"""src/optimizer/optimize_ops.py

Optimizes each generated kernel for the *current* GPU.

Original repo version had a hard-coded global output path and a syntax error.
This version:
- Accepts explicit paths (works for per-project runs)
- Auto-detects hardware specs (best-effort)
- Fixes logging/syntax issues

Usage:
  python -m src.optimizer.optimize_ops <io_parent_dir> \
      --generated-base <generated_kernels_dir> \
      --optimized-base <optimized_kernels_dir>

Inputs:
- io_parent_dir: projects/<name>/profiler/individual_ops
- generated-base: projects/<name>/kernels/generated/individual_op_kernels

Output:
- optimized-base: projects/<name>/kernels/optimized/individual_op_kernels
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import torch

import src.optimizer.generator as gen
import src.optimizer.GPUprofiler as gpu
from src.llm_config import resolve_llm_config


def _safe_get_gpu_specs(device_index: int | None = None) -> Dict[str, Any]:
    if not torch.cuda.is_available():
        return {"cuda_available": False}

    idx = torch.cuda.current_device() if device_index is None else int(device_index)
    try:
        return gpu.get_gpu_specs(device_index=idx)
    except Exception:
        props = torch.cuda.get_device_properties(idx)
        return {
            "cuda_available": True,
            "device_index": idx,
            "gpu_name": props.name,
            "compute_capability": f"{props.major}.{props.minor}",
            "total_memory_gb": float(props.total_memory) / (1024**3),
            "multi_processor_count": int(props.multi_processor_count),
        }


def optimization_loop(
    gpu_specs: Dict[str, Any],
    paths: Dict[str, Path],
    *,
    provider: str,
    model: str,
    iterations: int,
) -> None:
    """Optimize a single op kernel."""

    out_dir = paths["out_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)

    # Baseline profile (compile in temp dir)
    print("\nMeasuring baseline...")
    with tempfile.TemporaryDirectory() as tmp:
        paths["tmp_dir"] = Path(tmp)
        (paths["tmp_dir"] / "kernel.cu").write_text(
            (paths["op_dir"] / "kernel.cu").read_text(), encoding="utf-8"
        )
        baseline_stats, _ = gpu.profile_kernel(paths, baseline=True)
        best_stats = dict(baseline_stats)
        best_kernel_code = (paths["op_dir"] / "kernel.cu").read_text(encoding="utf-8")

    (out_dir / "kernel_baseline.cu").write_text(best_kernel_code, encoding="utf-8")

    improvement_log: List[Dict[str, Any]] = []

    for iteration in range(iterations):
        print(f"\nIteration {iteration}:")
        with tempfile.TemporaryDirectory() as tmp:
            paths["tmp_dir"] = Path(tmp)

            print("\tBeginning generation...")
            improvement_description, is_valid = gen.generate(
                best_kernel_code,
                gpu_specs,
                improvement_log,
                paths,
                model=model,
                provider=provider,
            )
            print("\tFinished generation.")
            print(f"\t\t- Desc: {improvement_description}")
            print(f"\t\t- Status: {is_valid}")

            if not is_valid:
                continue

            print("\tBeginning Profiler...")
            current_stats, _ = gpu.profile_kernel(paths)
            print("\tFinished Profiler.")

            speedup_vs_baseline = baseline_stats["mean_time_ms"] / current_stats["mean_time_ms"]
            speedup_vs_best = best_stats["mean_time_ms"] / current_stats["mean_time_ms"]

            log_entry: Dict[str, Any] = {
                "iteration": iteration,
                "attempted": improvement_description,
                "results": current_stats,
                "speedup_vs_baseline": speedup_vs_baseline,
                "speedup_vs_best": speedup_vs_best,
            }
            print(f"\t\t- speedup_vs_best: {speedup_vs_best:.3f}x")

            if current_stats["mean_time_ms"] < best_stats["mean_time_ms"]:
                log_entry["is_best"] = True
                best_stats = dict(current_stats)
                best_kernel_code = (paths["tmp_dir"] / "kernel.cu").read_text(encoding="utf-8")
                (out_dir / "kernel.cu").write_text(best_kernel_code, encoding="utf-8")
                (out_dir / f"kernel_iter_{iteration}.cu").write_text(best_kernel_code, encoding="utf-8")
            else:
                log_entry["is_best"] = False

            improvement_log.append(log_entry)

    (out_dir / "improvement_log.json").write_text(json.dumps(improvement_log, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print("Optimization Complete!")
    print("=" * 60)
    print(f"Baseline: {baseline_stats['mean_time_ms']:.3f} ms")
    print(f"Best:     {best_stats['mean_time_ms']:.3f} ms")
    print(f"Speedup:  {baseline_stats['mean_time_ms'] / best_stats['mean_time_ms']:.2f}x")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("io_parent_dir", help="Directory with per-op input/output entries")
    ap.add_argument("--generated-base", default="kernels/generated/individual_op_kernels")
    ap.add_argument("--optimized-base", default=None)
    ap.add_argument("--iterations", type=int, default=10)
    ap.add_argument("--provider", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--device-index", type=int, default=None)
    args = ap.parse_args()

    io_parent_dir = Path(args.io_parent_dir)
    gen_base = Path(args.generated_base)
    opt_base = Path(args.optimized_base) if args.optimized_base else Path("kernels/optimized/individual_op_kernels")

    if not io_parent_dir.exists():
        raise SystemExit(f"io_parent_dir not found: {io_parent_dir}")
    if not gen_base.exists():
        raise SystemExit(f"generated-base not found: {gen_base}")

    opt_base.mkdir(parents=True, exist_ok=True)

    try:
        cfg = resolve_llm_config(args.provider, args.model)
    except Exception as exc:
        raise SystemExit(str(exc))
    provider = cfg["provider"]
    model = cfg["model"]

    gpu_specs = _safe_get_gpu_specs(args.device_index)
    print(f"[optimizer] provider={provider} model={model}")

    op_dirs = sorted([p for p in gen_base.glob("*") if p.is_dir()])

    for op_dir in op_dirs:
        io_dir = io_parent_dir / op_dir.name
        if not io_dir.exists():
            print(f"[optimizer] skip {op_dir.name}: no i/o")
            continue

        out_dir = opt_base / op_dir.name
        out_dir.mkdir(parents=True, exist_ok=True)

        paths = {
            "io_dir": io_dir,
            "op_dir": op_dir,
            "out_dir": out_dir,
        }

        # Skip if already has an optimized kernel
        if (out_dir / "kernel.cu").exists():
            continue

        optimization_loop(gpu_specs, paths, provider=provider, model=model, iterations=int(args.iterations))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
