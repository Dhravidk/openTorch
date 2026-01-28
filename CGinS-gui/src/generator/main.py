"""src/generator/main.py

Main pipeline for CUDA kernel generation and validation.

Walks through each operation in a benchmark/profiler output dir to:
1. Monitor kernel and ATen calls
2. Generate CUDA kernel code via an LLM
3. Validate correctness through iterative refinement

This repo originally targeted benchmarks/, but we now also use it for per-project
profiling outputs:
  projects/<name>/profiler/individual_ops/<op_id>/entry_*.pt

Usage:
  python -m src.generator.main <io_dir> --output-base <out_dir>

LLM selection:
- Uses CLI flags if provided
- Else falls back to env vars:
    CGINS_LLM_PROVIDER, CGINS_LLM_MODEL
"""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import tempfile
from pathlib import Path

import torch
from tqdm import tqdm

import src.generator.generator as llm_gen
import src.generator.monitor as monitor
import src.generator.prompts.prompts as prompts
import src.generator.verifier as verify
from src.llm_config import resolve_llm_config


def _pick_llm(provider: str | None, model: str | None) -> tuple[str, str]:
    try:
        cfg = resolve_llm_config(provider, model)
        return cfg["provider"], cfg["model"]
    except Exception as exc:
        raise SystemExit(str(exc))


def _generate_kernel(conversation_history: list[dict], provider: str, model: str) -> str:
    if provider == "openai":
        return llm_gen.chatgpt_generator(conversation_history, model=model)
    if provider == "gemini":
        return llm_gen.gemini_generator(conversation_history, model=model)
    if provider == "ollama":
        # Ollama helper takes a single msg; flatten the conversation.
        flattened = "\n".join([f"{m['role']}: {m['content']}" for m in conversation_history])
        return llm_gen.ollama_generator(flattened, model=model)
    # default anthropic
    return llm_gen.anthropic_generator(conversation_history, model=model)


def validate_with_retries(
    output_dir: Path,
    entry_files: list[str],
    conversation_history: list[dict],
    *,
    provider: str,
    model: str,
    max_attempts: int,
) -> bool:
    """Attempt to validate and fix kernel code up to max_attempts times."""

    kernel_dir = output_dir / "kernel"
    kernel_dir.mkdir(parents=True, exist_ok=True)

    for attempt in range(max_attempts + 1):
        try:
            cu_code = _generate_kernel(conversation_history, provider, model)
            conversation_history.append({"role": "assistant", "content": cu_code})
        except Exception as e:
            print(f"Failed generation on attempt {attempt}: {e}")
            return False

        tmpdir = Path(tempfile.mkdtemp(prefix="gins_verifier_"))

        # Save newest kernel
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "kernel.cu").write_text(cu_code, encoding="utf-8")

        is_valid = True
        for i, entry_file in enumerate(tqdm(entry_files, desc="Input Tests")):
            log_file_loc = output_dir / "attempts" / f"log-{attempt}-{i}.txt"
            os.makedirs(log_file_loc.parent, exist_ok=True)

            call_success, exec_success, feedback = verify.validate_kernel(
                cu_code, entry_file, log_file_loc, tmpdir
            )

            print(feedback)

            is_valid = is_valid and call_success and exec_success
            if not is_valid:
                # archive failed attempt
                (kernel_dir / f"kernel-{attempt}-{i}.cu").write_text(cu_code, encoding="utf-8")
                conversation_history.append({"role": "user", "content": feedback})
                break

        # cleanup tmp dir
        try:
            shutil.rmtree(tmpdir)
        except Exception:
            pass

        if is_valid:
            print(f"SUCCESSFUL on attempt {attempt + 1}")
            (kernel_dir / f"kernel-{attempt}-g.cu").write_text(cu_code, encoding="utf-8")
            return True

    return False


def process_function(
    entry_files: list[str],
    op_dir: Path,
    *,
    provider: str,
    model: str,
    max_attempts: int,
) -> bool:
    """Process all profiled calls for a given function."""

    first_call = torch.load(entry_files[0], map_location="cpu", weights_only=False)
    first_args = first_call.get("args", [])
    first_kwargs = first_call.get("kwargs", {})

    function_name = first_call.get("function_name")
    if not function_name:
        print("Skipping: no function_name stored")
        return False

    context = {
        "torch": torch,
        "F": torch.nn.functional,
        "args": first_args,
        "kwargs": first_kwargs,
    }

    exec_str = f"{function_name}(*args, **kwargs)"

    conversation_history: list[dict] = []

    try:
        op_details = monitor.profile_single_op(context, exec_str)
    except Exception as e:
        print(e)
        return False

    call_list = []
    for entry_file in entry_files:
        try:
            entry = torch.load(entry_file, map_location="cpu", weights_only=False)
            call_list.append(entry)
        except Exception as e:
            print(f"Error loading {entry_file}: {e}")
            continue

    if not call_list:
        print(f"Failed to load any entries for {function_name}")
        return False

    prompt = prompts.generate_full_llm_prompt(call_list, function_name, op_details)
    conversation_history.append({"role": "user", "content": prompt})

    success = validate_with_retries(
        op_dir,
        entry_files,
        conversation_history,
        provider=provider,
        model=model,
        max_attempts=max_attempts,
    )

    if success:
        (op_dir / "success").write_text("passed", encoding="utf-8")

    return success


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("io_dir", help="Directory containing per-op subfolders with entry_*.pt")
    ap.add_argument("--output-base", default="kernels/generated")
    ap.add_argument("--max-attempts", type=int, default=5)
    ap.add_argument("--provider", default=None)
    ap.add_argument("--model", default=None)
    args = ap.parse_args()

    io_dir = Path(args.io_dir)
    output_base = Path(args.output_base)
    max_attempts = int(args.max_attempts)

    provider, model = _pick_llm(args.provider, args.model)
    print(f"[generator] provider={provider} model={model}")

    if not io_dir.exists():
        raise SystemExit(f"Input dir not found: {io_dir}")

    function_dirs = sorted(glob.glob(os.path.join(str(io_dir), "*")))

    failures = 0
    for func_dir in tqdm(function_dirs, desc="Processing functions"):
        if not os.path.isdir(func_dir):
            continue

        entry_files = sorted(glob.glob(os.path.join(func_dir, "entry_*.pt")))
        if not entry_files:
            continue

        # Use folder name as op_id; generator writes using function_name-derived id anyway
        op_id = os.path.basename(func_dir)
        op_dir = output_base / "individual_op_kernels" / op_id
        op_dir.mkdir(parents=True, exist_ok=True)

        if (op_dir / "success").exists():
            continue

        ok = process_function(
            entry_files,
            op_dir,
            provider=provider,
            model=model,
            max_attempts=max_attempts,
        )
        if not ok:
            failures += 1

    if failures:
        print(f"[generator] failed ops: {failures}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
