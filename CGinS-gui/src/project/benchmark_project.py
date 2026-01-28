"""src/project/benchmark_project.py

Compare PyTorch baseline vs CGinS bundle for a project.

Usage:
  python -m src.project.benchmark_project --project-dir projects/<name>
  python -m src.project.benchmark_project --project-dir projects/<name> --bundle /path/to/bundle.cgins
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List

import torch

from cgins_runtime import applied
from src.project.profile_project import (
    _load_example_inputs,
    _load_mode_a_model,
    _load_mode_b_model,
    _move_to_device,
)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _latest_bundle(export_dir: Path) -> Path | None:
    bundles = sorted(export_dir.glob("*.cgins"), key=lambda p: p.stat().st_mtime, reverse=True)
    return bundles[0] if bundles else None


def _percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    vals = sorted(values)
    k = max(0, min(len(vals) - 1, int(round((p / 100.0) * (len(vals) - 1)))))
    return vals[k]


def _stats(values: List[float]) -> Dict[str, Any]:
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "mean_ms": statistics.mean(values),
        "median_ms": statistics.median(values),
        "p95_ms": _percentile(values, 95),
        "min_ms": min(values),
        "max_ms": max(values),
    }


def _time_cuda(fn, iters: int, warmup: int) -> List[float]:
    for _ in range(warmup):
        fn()
        torch.cuda.synchronize()

    times: List[float] = []
    for _ in range(iters):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        fn()
        end.record()
        torch.cuda.synchronize()
        times.append(start.elapsed_time(end))
    return times


def _time_cpu(fn, iters: int, warmup: int) -> List[float]:
    for _ in range(warmup):
        fn()

    times: List[float] = []
    for _ in range(iters):
        t0 = time.perf_counter()
        fn()
        t1 = time.perf_counter()
        times.append((t1 - t0) * 1000.0)
    return times


def _load_model(project_dir: Path) -> torch.nn.Module:
    model_dir = project_dir / "model"
    model_py = model_dir / "model.py"
    weights_pt = model_dir / "weights.pt"
    full_model_pt = model_dir / "full_model.pt"

    meta = _read_json(project_dir / "project.json", {})
    mode = str(meta.get("mode", "A")).upper()

    if mode == "B":
        if not full_model_pt.exists():
            raise SystemExit(f"Mode B requires pickled full model at: {full_model_pt}")
        return _load_mode_b_model(model_py if model_py.exists() else None, full_model_pt)

    if not model_py.exists():
        raise SystemExit(f"Missing model code: {model_py}")
    return _load_mode_a_model(model_py, weights_pt if weights_pt.exists() else None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-dir", required=True)
    ap.add_argument("--bundle", default=None)
    ap.add_argument("--iters", type=int, default=30)
    ap.add_argument("--warmup", type=int, default=5)
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    project_dir = Path(args.project_dir).resolve()
    if not project_dir.exists():
        raise SystemExit(f"Project dir not found: {project_dir}")

    export_dir = project_dir / "export"
    bundle = Path(args.bundle).resolve() if args.bundle else _latest_bundle(export_dir)
    has_bundle = bool(bundle and bundle.exists())
    if not has_bundle:
        print("No bundle found. Running baseline-only benchmark (PyTorch).")

    inputs_dir = project_dir / "inputs"
    example_inputs_pt = inputs_dir / "example_inputs.pt"
    if not example_inputs_pt.exists():
        raise SystemExit(f"Missing example inputs: {example_inputs_pt}")

    model = _load_model(project_dir)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    model.eval()

    args_list, kwargs_dict = _load_example_inputs(example_inputs_pt)
    args_list = _move_to_device(args_list, device)
    kwargs_dict = _move_to_device(kwargs_dict, device)

    def forward():
        return model(*args_list, **kwargs_dict)

    timer = _time_cuda if device.type == "cuda" else _time_cpu

    with torch.no_grad():
        baseline_times = timer(forward, args.iters, args.warmup)

    bundle_times: List[float] = []
    if has_bundle:
        with torch.no_grad():
            with applied(bundle, verbose=False):
                bundle_times = timer(forward, args.iters, args.warmup)

    baseline_stats = _stats(baseline_times)
    bundle_stats = _stats(bundle_times)

    speedup = None
    if baseline_stats.get("mean_ms") and bundle_stats.get("mean_ms"):
        speedup = baseline_stats["mean_ms"] / bundle_stats["mean_ms"]

    result = {
        "project_dir": str(project_dir),
        "bundle_path": str(bundle) if has_bundle else None,
        "bundle_status": "ok" if has_bundle else "missing",
        "device": str(device),
        "baseline": baseline_stats,
        "bundle": bundle_stats,
        "speedup": speedup,
    }

    output_path = Path(args.output) if args.output else (project_dir / "benchmark.json")
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
