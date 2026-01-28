"""
src/llm_config.py
Resolve LLM provider/model/key configuration from cgins_config.json + env.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Tuple


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _normalize_provider(provider: str) -> str:
    p = (provider or "").strip().lower()
    if p in ("gpt",):
        return "openai"
    if p in ("google",):
        return "gemini"
    if p in ("local",):
        return "ollama"
    return p or "anthropic"


def _default_model(provider: str) -> str:
    if provider == "openai":
        return "gpt-4o"
    if provider == "gemini":
        return "gemini-2.5-flash"
    if provider == "ollama":
        # local model; user can set qwen2.5:7b or similar
        return "qwen2.5:7b"
    return "claude-opus-4-5-20251101"


def resolve_llm_config(
    provider: str | None = None,
    model: str | None = None,
) -> Dict[str, Any]:
    cfg_path = _repo_root() / "cgins_config.json"
    cfg = _read_json(cfg_path, {})

    env_provider = os.getenv("CGINS_LLM_PROVIDER")
    env_model = os.getenv("CGINS_LLM_MODEL")

    resolved_provider = _normalize_provider(provider or env_provider or cfg.get("llm_provider") or "anthropic")
    resolved_model = model or env_model or cfg.get("llm_model") or _default_model(resolved_provider)

    openai_key = cfg.get("openai_api_key") or os.getenv("OPENAI_API_KEY", "")
    anthropic_key = cfg.get("anthropic_api_key") or os.getenv("ANTHROPIC_API_KEY", "")
    google_key = cfg.get("google_api_key") or os.getenv("GOOGLE_API_KEY", "")

    base_url = (
        os.getenv("CGINS_LLM_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("OPENAI_API_BASE")
        or None
    )

    ollama_host = os.getenv("CGINS_OLLAMA_HOST") or os.getenv("OLLAMA_HOST") or None
    if resolved_provider == "ollama" and ollama_host:
        os.environ["OLLAMA_HOST"] = ollama_host

    return {
        "provider": resolved_provider,
        "model": resolved_model,
        "openai_api_key": openai_key,
        "anthropic_api_key": anthropic_key,
        "google_api_key": google_key,
        "base_url": base_url,
        "ollama_host": ollama_host,
    }
