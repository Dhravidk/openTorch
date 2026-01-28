#!/usr/bin/env python3
"""Comprehensive CGinS test suite runner (no external deps).

Checks:
  - Config validity (provider/model/key consistency)
  - Backend and frontend health
  - Project file requirements
  - Generator supports OpenAI Responses for gpt-5/gpt-4.1 models
Optional:
  - Probe OpenAI API key via responses endpoint
  - Run pipeline jobs (profile/generate/optimize/export/benchmark/smoke)
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _http(method: str, url: str, payload: Dict[str, Any] | None = None) -> Tuple[int, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read()
            try:
                return resp.status, json.loads(body.decode("utf-8"))
            except Exception:
                return resp.status, body.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read()
        try:
            return exc.code, json.loads(body.decode("utf-8"))
        except Exception:
            return exc.code, body.decode("utf-8", errors="replace")
    except Exception as exc:
        return 0, {"error": str(exc)}


def _redact(s: str) -> str:
    if not s:
        return ""
    if len(s) <= 8:
        return "****"
    return s[:3] + "..." + s[-4:]


def _validate_llm_config(cfg: Dict[str, Any]) -> Tuple[bool, str]:
    provider = (cfg.get("llm_provider") or "anthropic").strip().lower()
    model = (cfg.get("llm_model") or "").strip().lower()

    if provider in ("openai", "gpt"):
        if not cfg.get("openai_api_key"):
            return False, "OpenAI provider selected but OPENAI_API_KEY is empty."
        if "claude" in model or "gemini" in model:
            return False, "OpenAI provider selected but model looks Anthropic/Gemini."
    elif provider in ("anthropic", "claude"):
        if not cfg.get("anthropic_api_key"):
            return False, "Anthropic provider selected but ANTHROPIC_API_KEY is empty."
        if "gpt" in model or "gemini" in model:
            return False, "Anthropic provider selected but model looks OpenAI/Gemini."
    elif provider in ("gemini", "google"):
        if not cfg.get("google_api_key"):
            return False, "Gemini provider selected but GOOGLE_API_KEY is empty."
        if "gpt" in model or "claude" in model:
            return False, "Gemini provider selected but model looks OpenAI/Anthropic."
    elif provider in ("ollama",):
        pass
    else:
        return False, f"Unsupported provider: {provider}"

    return True, "ok"


def _check_generator_responses_support(repo_root: Path) -> Tuple[bool, str]:
    gen_path = repo_root / "src" / "generator" / "generator.py"
    if not gen_path.exists():
        return False, "generator.py not found"
    text = gen_path.read_text(encoding="utf-8", errors="ignore")
    if "_openai_needs_responses" in text and "responses.create" in text:
        return True, "OpenAI Responses API support detected"
    return False, "OpenAI Responses API support not detected (gpt-5 models will fail)"


def _load_project_meta(project_dir: Path) -> Dict[str, Any]:
    return _read_json(project_dir / "project.json", {})


def _check_project_files(project_dir: Path) -> Tuple[bool, str]:
    meta = _load_project_meta(project_dir)
    mode = str(meta.get("mode", "A")).upper()
    model_dir = project_dir / "model"
    inputs_dir = project_dir / "inputs"

    example_inputs = inputs_dir / "example_inputs.pt"
    if not example_inputs.exists():
        return False, f"Missing example_inputs.pt at {example_inputs}"

    if mode == "B":
        full_model = model_dir / "full_model.pt"
        if not full_model.exists():
            return False, f"Mode B missing full_model.pt at {full_model}"
    else:
        model_py = model_dir / "model.py"
        if not model_py.exists():
            return False, f"Mode A missing model.py at {model_py}"

    return True, "ok"


def _probe_openai(api_key: str, model: str) -> Tuple[bool, str]:
    try:
        from openai import OpenAI  # type: ignore
    except Exception as exc:
        return False, f"openai package not available: {exc}"

    try:
        client = OpenAI(api_key=api_key)
        resp = client.responses.create(
            model=model,
            input=[{"role": "user", "content": "ping"}],
            max_output_tokens=10,
        )
        text = getattr(resp, "output_text", None)
        if not text:
            return False, "OpenAI probe returned no output_text"
        return True, "OpenAI probe ok"
    except Exception as exc:
        return False, f"OpenAI probe failed: {exc}"


def _run_job(backend: str, project: str, job_type: str, timeout_s: int) -> Tuple[bool, str]:
    status, resp = _http("POST", f"{backend}/walker/start_job", {"project_name": project, "job_type": job_type})
    if status >= 400 or not isinstance(resp, dict):
        return False, f"start_job failed: {resp}"
    out = (resp.get("data") or resp.get("result") or resp)
    job = (out.get("reports") or [out])[0] if isinstance(out, dict) else out
    job_id = job.get("job_id") if isinstance(job, dict) else None
    if not job_id:
        return False, f"missing job_id: {job}"

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        status, data = _http("POST", f"{backend}/walker/get_job", {"project_name": project, "job_id": job_id})
        if status >= 400:
            return False, f"get_job failed: {data}"
        out2 = (data.get("data") or data.get("result") or data)
        job2 = (out2.get("reports") or [out2])[0] if isinstance(out2, dict) else out2
        state = (job2.get("status") or "").lower() if isinstance(job2, dict) else ""
        if state in ("success", "failed", "error", "done"):
            return state == "success", f"{job_type} status={state}"
        time.sleep(2)
    return False, f"{job_type} timed out after {timeout_s}s"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default=os.getenv("CGINS_BACKEND_URL", "http://localhost:8000"))
    parser.add_argument("--frontend", default=os.getenv("CGINS_FRONTEND_URL", "http://localhost:3000"))
    parser.add_argument("--project", default=None)
    parser.add_argument("--probe-openai", action="store_true")
    parser.add_argument("--pipeline", default="", help="comma list: profile,generate,optimize,export,benchmark,smoke")
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    cfg = _read_json(repo_root / "cgins_config.json", {})

    results: List[Tuple[str, bool, str]] = []

    ok, msg = _validate_llm_config(cfg)
    results.append(("config.validate_llm", ok, msg))

    ok, msg = _check_generator_responses_support(repo_root)
    results.append(("generator.responses_support", ok, msg))

    status, _ = _http("GET", f"{args.backend}/walkers")
    results.append(("backend.walkers", status == 200, f"status={status}"))

    status, _ = _http("GET", f"{args.frontend}/api/projects")
    results.append(("frontend.projects", status == 200, f"status={status}"))

    if args.project:
        proj_dir = repo_root / "projects" / args.project
        ok, msg = _check_project_files(proj_dir)
        results.append((f"project.files.{args.project}", ok, msg))

    if args.probe_openai:
        model = cfg.get("llm_model", "gpt-5.1-codex-mini")
        key = cfg.get("openai_api_key") or os.getenv("OPENAI_API_KEY", "")
        if not key:
            results.append(("openai.probe", False, "OpenAI key missing"))
        else:
            ok, msg = _probe_openai(key, model)
            results.append(("openai.probe", ok, msg))

    if args.pipeline and args.project:
        steps = [s.strip() for s in args.pipeline.split(",") if s.strip()]
        for step in steps:
            ok, msg = _run_job(args.backend, args.project, step, args.timeout)
            results.append((f"pipeline.{step}", ok, msg))

    # Summary
    print("\nTEST SUMMARY")
    exit_code = 0
    for name, ok, msg in results:
        status = "PASS" if ok else "FAIL"
        print(f"{status} {name} - {msg}")
        if not ok:
            exit_code = 1

    # Redacted config echo for debugging
    if cfg:
        red = dict(cfg)
        if "openai_api_key" in red:
            red["openai_api_key"] = _redact(str(red["openai_api_key"]))
        if "anthropic_api_key" in red:
            red["anthropic_api_key"] = _redact(str(red["anthropic_api_key"]))
        if "google_api_key" in red:
            red["google_api_key"] = _redact(str(red["google_api_key"]))
        print("\nCONFIG (redacted)")
        print(json.dumps(red, indent=2))

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
