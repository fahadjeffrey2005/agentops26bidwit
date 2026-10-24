"""Settings, read once from environment variables and checked at startup.

A bad setting stops the program immediately with a clear message, instead of
failing halfway through a run. Secrets (API keys) are never stored here: the
SDK that needs a key reads it from the environment itself.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import Field

from .contracts import Strict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent


class Settings(Strict):
    llm: Literal["on", "off"] = "on"                    # off: no AI calls at all, parts use their rules
    llm_chain: str = Field(default="groq:openai/gpt-oss-120b,groq:qwen/qwen3.8-27b,groq:openai/gpt-oss-20b,gemini:gemini-3.6-flash",
                           pattern=r"^\s*(groq|gemini):[\w./-]+(\s*,\s*(groq|gemini):[\w./-]+)*\s*$", max_length=500)
    llm_max_calls: int = Field(default=150, ge=1, le=500)
    data_dir: Path = REPO_DIR / "data"
    runs_dir: Path = REPO_DIR / "runs"
    max_upload_mb: int = Field(default=20, ge=1, le=100)


def load_settings(env: dict[str, str] | None = None) -> Settings:
    env = dict(os.environ if env is None else env)
    raw = {
        "llm": env.get("BIDWIT_LLM"),
        "llm_chain": env.get("BIDWIT_LLM_CHAIN"),
        "llm_max_calls": env.get("BIDWIT_LLM_MAX_CALLS"),
        "data_dir": env.get("BIDWIT_DATA_DIR"),
        "runs_dir": env.get("BIDWIT_RUNS_DIR"),
        "max_upload_mb": env.get("BIDWIT_MAX_UPLOAD_MB"),
    }
    raw = {k: v for k, v in raw.items() if v not in (None, "")}
    return Settings(**raw)
