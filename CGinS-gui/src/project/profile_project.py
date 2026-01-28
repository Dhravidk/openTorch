"""src/project/profile_project.py

Project profiler:
- Loads a user model (Mode A: code + optional weights, Mode B: pickled full model)
- Runs a forward pass using inputs/example_inputs.pt
- Wraps torch.nn.functional.* to record call inputs/outputs
- Saves entry_*.pt under: <project>/profiler/individual_ops/<op_id>/

This is the bridge between "user model" and CGinS' existing generator/optimizer pipeline.

Example inputs format:
  torch.save({"args": [...], "kwargs": {...}}, "example_inputs.pt")

Notes:
- Mode B is **pickled models only** (torch.save(model)). TorchScript is not supported here.
"""

from __future__ import annotations

import argparse
import glob
import inspect
import json
import os
import re
import shutil
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any, Dict, List, Tuple

import torch
import torch.nn.functional as F

# Functions to skip wrapping (helpers / internals / weird cases)
SKIP_SUBSTRINGS = [
    "torch_function",
    "storage",
    "result_type",
    "dtype",
]


def _safe_mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _load_example_inputs(path: Path) -> Tuple[List[Any], Dict[str, Any]]:
    obj = torch.load(path, map_location="cpu", weights_only=False)

    # Accept either dict or (args, kwargs)
    if isinstance(obj, dict):
        args = obj.get("args", [])
        kwargs = obj.get("kwargs", {})
        if not isinstance(args, list):
            raise TypeError("example_inputs.pt: 'args' must be a list")
        if not isinstance(kwargs, dict):
            raise TypeError("example_inputs.pt: 'kwargs' must be a dict")
        return args, kwargs

    if isinstance(obj, (tuple, list)) and len(obj) == 2:
        args, kwargs = obj
        if not isinstance(args, (list, tuple)) or not isinstance(kwargs, dict):
            raise TypeError("example_inputs.pt: expected (args, kwargs)")
        return list(args), kwargs

    raise TypeError(
        "example_inputs.pt must be a dict {args:..., kwargs:...} or a 2-tuple (args, kwargs)"
    )


def _move_to_device(x: Any, device: torch.device) -> Any:
    if torch.is_tensor(x):
        return x.to(device)
    if isinstance(x, (list, tuple)):
        return type(x)(_move_to_device(v, device) for v in x)
    if isinstance(x, dict):
        return {k: _move_to_device(v, device) for k, v in x.items()}
    return x


def _sanitize_op_id(function_name: str) -> str:
    # Keep it consistent with generator: dots -> underscores
    return re.sub(r"[^A-Za-z0-9_]+", "_", function_name.replace(".", "_"))


@dataclass
class CallRecord:
    function_name: str
    args: List[Any]
    kwargs: Dict[str, Any]
    output: Any
    signature: Dict[str, Any]


class FunctionalCallRecorder:
    def __init__(self, max_per_op: int = 200):
        self.calls: Dict[str, List[Dict[str, Any]]] = {}
        self._wrapped = set()
        self.max_per_op = max_per_op

    def wrap_all(self) -> None:
        for name in dir(F):
            if name.startswith("_"):
                continue
            if any(sub in name for sub in SKIP_SUBSTRINGS):
                continue
            obj = getattr(F, name)
            if callable(obj):
                self._wrap_function(F, name)

    def _wrap_function(self, module, func_name: str) -> None:
        func = getattr(module, func_name)
        if func in self._wrapped:
            return
        self._wrapped.add(func)

        module_path = module.__name__

        # Signature capture (parameter order & defaults)
        try:
            sig = inspect.signature(func)
            params = list(sig.parameters.keys())
            defaults: Dict[str, Any] = {}
            for p_name, p in sig.parameters.items():
                if p.default != inspect.Parameter.empty:
                    defaults[p_name] = p.default
        except Exception:
            params = []
            defaults = {}

        @wraps(func)
        def wrapper(*args, **kwargs):
            key = f"{module_path}.{func_name}"

            # limit explosion
            if len(self.calls.get(key, [])) >= self.max_per_op:
                return func(*args, **kwargs)

            # serialize args/kwargs to CPU (lossless for tensors)
            ser_args = [a.detach().cpu() if torch.is_tensor(a) else a for a in args]
            ser_kwargs = {
                k: (v.detach().cpu() if torch.is_tensor(v) else v)
                for k, v in kwargs.items()
            }

            out = func(*args, **kwargs)

            # Only support tensor outputs for now (generator/verifier expects a Tensor)
            if torch.is_tensor(out):
                ser_out = out.detach().cpu()
            else:
                return out

            self.calls.setdefault(key, []).append(
                {
                    "function_name": key,
                    "args": ser_args,
                    "kwargs": ser_kwargs,
                    "output": ser_out,
                    "signature": {"params": params, "defaults": defaults},
                }
            )

            return out

        setattr(module, func_name, wrapper)


def _load_mode_a_model(model_py: Path, weights_pt: Path | None) -> torch.nn.Module:
    code = model_py.read_text(encoding="utf-8")

    # Exec user code in isolated globals
    g: Dict[str, Any] = {"torch": torch}
    exec(compile(code, str(model_py), "exec"), g, g)

    model = None
    if "build_model" in g and callable(g["build_model"]):
        model = g["build_model"]()
    elif "Model" in g:
        model = g["Model"]()  # type: ignore

    if model is None or not isinstance(model, torch.nn.Module):
        raise ValueError(
            "Mode A requires model.py to define build_model() or a Model(nn.Module) class"
        )

    if weights_pt and weights_pt.exists():
        state = torch.load(weights_pt, map_location="cpu", weights_only=False)
        if isinstance(state, dict):
            try:
                model.load_state_dict(state, strict=False)
            except Exception:
                # some users save {'state_dict': ...}
                if "state_dict" in state and isinstance(state["state_dict"], dict):
                    model.load_state_dict(state["state_dict"], strict=False)
                else:
                    raise

    model.eval()
    return model


def _load_mode_b_model(model_py: Path | None, full_model_pt: Path) -> torch.nn.Module:
    # If model.py exists, exec it first to register custom classes for unpickling.
    if model_py and model_py.exists():
        code = model_py.read_text(encoding="utf-8")
        g: Dict[str, Any] = {"torch": torch}
        exec(compile(code, str(model_py), "exec"), g, g)

    obj = torch.load(full_model_pt, map_location="cpu", weights_only=False)
    if not isinstance(obj, torch.nn.Module):
        raise TypeError(
            "Mode B only supports pickled torch.nn.Module saved via torch.save(model, path)."
        )
    obj.eval()
    return obj


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-dir", required=True)
    ap.add_argument("--max-per-op", type=int, default=200)
    args = ap.parse_args()

    project_dir = Path(args.project_dir).resolve()
    model_dir = project_dir / "model"
    inputs_dir = project_dir / "inputs"
    profiler_dir = project_dir / "profiler"
    ops_dir = profiler_dir / "individual_ops"

    if not project_dir.exists():
        raise SystemExit(f"Project dir not found: {project_dir}")

    _safe_mkdir(ops_dir)

    project_meta_path = project_dir / "project.json"
    meta = {}
    if project_meta_path.exists():
        meta = json.loads(project_meta_path.read_text(encoding="utf-8"))

    mode = str(meta.get("mode", "A")).upper()

    model_py = model_dir / "model.py"
    weights_pt = model_dir / "weights.pt"
    full_model_pt = model_dir / "full_model.pt"

    example_inputs_pt = inputs_dir / "example_inputs.pt"
    if not example_inputs_pt.exists():
        raise SystemExit(
            f"Missing example inputs: {example_inputs_pt}. This file is required for profiling."
        )

    if mode == "B":
        if not full_model_pt.exists():
            raise SystemExit(
                f"Mode B requires pickled full model at: {full_model_pt}"
            )
        model = _load_mode_b_model(model_py if model_py.exists() else None, full_model_pt)
    else:
        # Mode A
        if not model_py.exists():
            raise SystemExit(f"Missing model code: {model_py}")
        model = _load_mode_a_model(model_py, weights_pt if weights_pt.exists() else None)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)

    args_list, kwargs_dict = _load_example_inputs(example_inputs_pt)
    args_list = _move_to_device(args_list, device)
    kwargs_dict = _move_to_device(kwargs_dict, device)

    recorder = FunctionalCallRecorder(max_per_op=int(args.max_per_op))
    recorder.wrap_all()

    # Run forward pass
    with torch.no_grad():
        _ = model(*args_list, **kwargs_dict)
        if device.type == "cuda":
            torch.cuda.synchronize()

    # Export calls
    summary: Dict[str, Any] = {
        "project_dir": str(project_dir),
        "mode": mode,
        "device": str(device),
        "ops": {},
    }

    # Clear old entries so a re-profile doesn't mix incompatible shapes
    if ops_dir.exists():
        for d in ops_dir.glob("*"):
            if d.is_dir():
                shutil.rmtree(d)

    for func_name, entries in recorder.calls.items():
        op_id = _sanitize_op_id(func_name)
        out_dir = ops_dir / op_id
        _safe_mkdir(out_dir)

        for idx, entry in enumerate(entries):
            path = out_dir / f"entry_{idx:06d}.pt"
            torch.save(entry, path)

        # summary
        first = entries[0] if entries else {}
        summary["ops"][op_id] = {
            "function_name": func_name,
            "count": len(entries),
            "signature": first.get("signature", {"params": [], "defaults": {}}),
        }

    (profiler_dir / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    print(f"Profiled {len(summary['ops'])} ops")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
