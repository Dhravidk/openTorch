"""src/project/run_with_bundle.py

Smoke-test runner:
- Loads a project model
- Applies a .cgins bundle via cgins_runtime
- Runs the model forward with example inputs
- Prints timings (CUDA only)

This is intended to be called by the Jac app as a background job.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import torch

from cgins_runtime import applied
from src.project.profile_project import _load_example_inputs, _load_mode_a_model, _load_mode_b_model, _move_to_device


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-dir", required=True)
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--iters", type=int, default=10)
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    project_dir = Path(args.project_dir).resolve()
    bundle_path = Path(args.bundle).resolve()

    meta = _read_json(project_dir / "project.json", {})
    mode = str(meta.get("mode", "A")).upper()

    model_dir = project_dir / "model"
    inputs_dir = project_dir / "inputs"

    model_py = model_dir / "model.py"
    weights_pt = model_dir / "weights.pt"
    full_model_pt = model_dir / "full_model.pt"

    if mode == "B":
        model = _load_mode_b_model(model_py if model_py.exists() else None, full_model_pt)
    else:
        model = _load_mode_a_model(model_py, weights_pt if weights_pt.exists() else None)

    if not torch.cuda.is_available():
        raise SystemExit("CUDA is required for smoke test (bundle dispatch compiles CUDA extensions)")

    device = torch.device("cuda")
    model.to(device)
    model.eval()

    ex_inputs = inputs_dir / "example_inputs.pt"
    args_list, kwargs = _load_example_inputs(ex_inputs)
    args_list = _move_to_device(args_list, device)
    kwargs = _move_to_device(kwargs, device)

    # Measure baseline vs patched (very rough)
    def _time_forward(iters: int) -> float:
        starter, ender = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
        torch.cuda.synchronize()
        starter.record()
        with torch.no_grad():
            for _ in range(iters):
                _ = model(*args_list, **kwargs)
        ender.record()
        torch.cuda.synchronize()
        return float(starter.elapsed_time(ender)) / float(iters)

    print("[smoke] warmup baseline...")
    with torch.no_grad():
        for _ in range(args.warmup):
            _ = model(*args_list, **kwargs)
    torch.cuda.synchronize()

    baseline_ms = _time_forward(args.iters)
    print(f"[smoke] baseline mean ms/iter: {baseline_ms:.4f}")

    print("[smoke] applying bundle and warming up...")
    with applied(bundle_path, verbose=bool(args.verbose)):
        with torch.no_grad():
            for _ in range(args.warmup):
                _ = model(*args_list, **kwargs)
        torch.cuda.synchronize()
        patched_ms = _time_forward(args.iters)

    print(f"[smoke] patched mean ms/iter: {patched_ms:.4f}")
    if patched_ms > 0:
        print(f"[smoke] speedup: {baseline_ms / patched_ms:.2f}x")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
