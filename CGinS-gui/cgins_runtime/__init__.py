"""cgins_runtime

A minimal runtime that can consume a CGinS export bundle (".cgins") and
monkey-patch torch.nn.functional.* to dispatch to generated kernels.

Design goals:
- Safe by default: fallback to original PyTorch if anything mismatches.
- Lazy compilation: each op kernel is compiled on first use, cached on disk.
- Zero external build system: uses torch.utils.cpp_extension.load_inline.

Bundle format:
- zip with:
  - manifest.json
  - kernels/<op_id>/kernel.cu
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import torch
from torch.utils.cpp_extension import load_inline


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _default_cache_dir() -> Path:
    # Works in WSL/Linux; user can override via CGINS_RUNTIME_CACHE_DIR
    env = os.getenv("CGINS_RUNTIME_CACHE_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return Path.home() / ".cache" / "cgins_runtime"


def _normalize_args_kwargs(args: Tuple[Any, ...], kwargs: Dict[str, Any], signature: Dict[str, Any]) -> Tuple[List[Any], Dict[str, Any]]:
    params = signature.get("params", []) or []
    defaults = signature.get("defaults", {}) or {}

    if not params:
        return list(args), dict(kwargs)

    normalized = list(args)
    remaining = dict(kwargs)

    for i in range(len(normalized), len(params)):
        p = params[i]
        if p in remaining:
            normalized.append(remaining.pop(p))
        elif p in defaults:
            normalized.append(defaults[p])
        else:
            break

    return normalized, remaining


def _move_to_cuda(x: Any) -> Any:
    if torch.is_tensor(x):
        return x.cuda()
    if isinstance(x, (list, tuple)):
        return type(x)(_move_to_cuda(v) for v in x)
    if isinstance(x, dict):
        return {k: _move_to_cuda(v) for k, v in x.items()}
    return x


def _extract_launch_signature(cuda_source: str) -> str:
    match = re.search(r"(torch::Tensor\s+launch\s*\([^)]*\))", cuda_source)
    if not match:
        raise ValueError("Could not find 'torch::Tensor launch(...)' signature in kernel.cu")
    return match.group(1)


class Bundle:
    def __init__(self, bundle_path: Path):
        self.bundle_path = Path(bundle_path).resolve()
        if not self.bundle_path.exists():
            raise FileNotFoundError(str(self.bundle_path))

        with zipfile.ZipFile(self.bundle_path, "r") as zf:
            manifest_bytes = zf.read("manifest.json")
        self.manifest = json.loads(manifest_bytes.decode("utf-8"))
        self.bundle_hash = _sha256_bytes(manifest_bytes)[:16]

    def iter_ops(self) -> List[Dict[str, Any]]:
        return list(self.manifest.get("ops", []) or [])

    def read_kernel(self, kernel_rel: str) -> str:
        with zipfile.ZipFile(self.bundle_path, "r") as zf:
            data = zf.read(kernel_rel)
        return data.decode("utf-8")


class Runtime:
    def __init__(self, bundle: Bundle, *, verbose: bool = False):
        self.bundle = bundle
        self.verbose = verbose
        self._compiled: Dict[str, Any] = {}
        self._originals: Dict[str, Callable] = {}

    def _compile_op(self, op_id: str, cuda_source: str) -> Any:
        cache_dir = _default_cache_dir() / self.bundle.bundle_hash / op_id
        cache_dir.mkdir(parents=True, exist_ok=True)

        # Use a stable module name per op+hash
        name = f"cgins_{self.bundle.bundle_hash}_{op_id}"

        sig = _extract_launch_signature(cuda_source)
        cpp_source = sig + ";"

        # load_inline caches builds by name+sources+build_directory
        module = load_inline(
            name=name,
            cpp_sources=cpp_source,
            cuda_sources=cuda_source,
            functions=["launch"],
            build_directory=str(cache_dir),
            with_cuda=True,
            verbose=self.verbose,
        )
        return module

    def _get_module(self, op_id: str, kernel_rel: str) -> Any:
        if op_id in self._compiled:
            return self._compiled[op_id]

        cuda_source = self.bundle.read_kernel(kernel_rel)
        module = self._compile_op(op_id, cuda_source)
        self._compiled[op_id] = module
        return module

    def apply(self) -> None:
        """Monkey-patch torch.nn.functional.* functions present in the bundle."""
        import torch.nn.functional as F

        for op in self.bundle.iter_ops():
            func_name = op.get("function_name")
            op_id = op.get("op_id")
            kernel_rel = op.get("kernel")
            signature = op.get("signature", {"params": [], "defaults": {}})

            if not func_name or not op_id or not kernel_rel:
                continue

            # Only patch torch.nn.functional.*
            prefix = "torch.nn.functional."
            if not str(func_name).startswith(prefix):
                continue

            attr = str(func_name)[len(prefix):]
            if not hasattr(F, attr):
                continue

            original = getattr(F, attr)
            if attr in self._originals:
                continue

            def make_wrapper(_orig: Callable, _op_id: str, _kernel_rel: str, _sig: Dict[str, Any]):
                def wrapper(*args, **kwargs):
                    # Fast fallback conditions
                    if not torch.cuda.is_available():
                        return _orig(*args, **kwargs)

                    # If no tensor args, don't dispatch.
                    has_tensor = any(torch.is_tensor(a) for a in args) or any(torch.is_tensor(v) for v in kwargs.values())
                    if not has_tensor:
                        return _orig(*args, **kwargs)

                    # Normalize -> positional only
                    pos_args, remaining = _normalize_args_kwargs(args, kwargs, _sig)
                    if remaining:
                        # Can't map kwargs reliably
                        return _orig(*args, **kwargs)

                    try:
                        mod = self._get_module(_op_id, _kernel_rel)
                        cuda_args = [_move_to_cuda(a) for a in pos_args]
                        out = mod.launch(*cuda_args)
                        return out
                    except Exception:
                        # Safety fallback
                        return _orig(*args, **kwargs)

                return wrapper

            setattr(F, attr, make_wrapper(original, str(op_id), str(kernel_rel), signature))
            self._originals[attr] = original

    def restore(self) -> None:
        """Restore original torch.nn.functional.* functions."""
        import torch.nn.functional as F

        for attr, orig in self._originals.items():
            if hasattr(F, attr):
                setattr(F, attr, orig)
        self._originals.clear()


@contextmanager
def applied(bundle_path: str | Path, *, verbose: bool = False):
    """Context manager that applies a bundle for the duration of the context."""
    b = Bundle(Path(bundle_path))
    rt = Runtime(b, verbose=verbose)
    rt.apply()
    try:
        yield rt
    finally:
        rt.restore()
