"""src/project/export_bundle.py

Creates a single-file export bundle (".cgins") that contains:
- manifest.json
- per-op kernel.cu files (optimized preferred, generated fallback)

The bundle is a zip archive with a stable internal layout.

This export is intended to be consumed by cgins_runtime (included in this repo)
or by the Jac app's "Run smoke test" action.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import torch


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _gpu_info() -> Dict[str, Any]:
    if not torch.cuda.is_available():
        return {"cuda_available": False}

    idx = torch.cuda.current_device()
    props = torch.cuda.get_device_properties(idx)
    return {
        "cuda_available": True,
        "device_index": idx,
        "name": props.name,
        "major": int(props.major),
        "minor": int(props.minor),
        "total_memory_gb": float(props.total_memory) / (1024**3),
        "multi_processor_count": int(props.multi_processor_count),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-dir", required=True)
    ap.add_argument("--output", default=None, help="Optional override output path")
    args = ap.parse_args()

    project_dir = Path(args.project_dir).resolve()
    meta = _read_json(project_dir / "project.json", {})
    project_name = str(meta.get("name") or project_dir.name)

    profiler_summary = _read_json(project_dir / "profiler" / "summary.json", {})
    ops_meta = profiler_summary.get("ops", {}) or {}

    gen_base = project_dir / "kernels" / "generated" / "individual_op_kernels"
    opt_base = project_dir / "kernels" / "optimized" / "individual_op_kernels"

    export_dir = project_dir / "export"
    export_dir.mkdir(parents=True, exist_ok=True)

    out_path = Path(args.output) if args.output else (export_dir / f"{project_name}.cgins")
    out_path = out_path.resolve()

    # Choose kernels: optimized preferred
    bundle_ops: List[Dict[str, Any]] = []
    kernel_blobs: Dict[str, bytes] = {}

    # If we have a profiler summary, use it as the source-of-truth
    op_ids = sorted(list(ops_meta.keys()))

    for op_id in op_ids:
        func_name = ops_meta.get(op_id, {}).get("function_name")
        sig = ops_meta.get(op_id, {}).get("signature", {"params": [], "defaults": {}})

        # locate kernel.cu
        kpath = None
        opt_k = opt_base / op_id / "kernel.cu"
        gen_k = gen_base / op_id / "kernel.cu"
        if opt_k.exists():
            kpath = opt_k
            source = "optimized"
        elif gen_k.exists():
            kpath = gen_k
            source = "generated"
        else:
            continue

        code_bytes = kpath.read_bytes()
        kernel_rel = f"kernels/{op_id}/kernel.cu"
        kernel_blobs[kernel_rel] = code_bytes

        bundle_ops.append(
            {
                "op_id": op_id,
                "function_name": func_name,
                "kernel": kernel_rel,
                "kernel_sha256": _sha256_bytes(code_bytes),
                "signature": sig,
                "source": source,
            }
        )

    manifest = {
        "format_version": 1,
        "project": project_name,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "gpu": _gpu_info(),
        "ops": bundle_ops,
    }

    # Write zip
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        for rel, blob in kernel_blobs.items():
            zf.writestr(rel, blob)

    print(f"Exported bundle: {out_path}")
    print(f"Ops included: {len(bundle_ops)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
