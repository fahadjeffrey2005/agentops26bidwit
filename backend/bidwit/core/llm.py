"""One AI client for every part: a chain of providers, schema-checked answers, a cache and a call budget.

    client = LLMClient.from_settings(settings)
    answer, info = client.ask(task="classify", system=..., user=..., schema=MyPydanticModel)

- Providers are tried in order (default: Groq gpt-oss-120b -> Groq qwen3.8-27b -> Groq gpt-oss-20b -> Gemini).
  A provider that is out of quota, missing its key, unknown, overloaded or keeps returning bad answers is
  skipped for the rest of the run; the next one is used. If all fail, LLMUnavailable is raised and the
  calling part falls back to its rules.
- Every answer is validated against the pydantic schema. Nothing unvalidated leaves this module.
- Answers are cached on disk by hash of (task, system, user, schema), not by provider, so a replay costs
  no calls even if a different provider answered the first time. Corrupt or invalid cache entries are ignored.
- API keys are read from the environment at call time (GROQ_API_KEY, GEMINI_API_KEY); never stored or logged.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .progress import step

M = TypeVar("M", bound=BaseModel)

GROQ_BASE = "https://api.groq.com/openai/v1"
DEFAULT_CHAIN = "groq:openai/gpt-oss-120b,groq:qwen/qwen3.8-27b,groq:openai/gpt-oss-20b,gemini:gemini-3.6-flash"
TIMEOUT_S = 90
SHORT_WAIT_MAX_S = 65.0                                # per-minute limits clear within a minute; per-day ones don't
GROQ_TPM = int(os.environ.get("BIDWIT_GROQ_TPM", "7000")) if os.environ.get("BIDWIT_GROQ_TPM", "7000").isdigit() else 7000  # under Groq's free 8k tokens/minute per model
GROQ_MAX_OUT = 4096                                    # cap the reply; Groq counts it against the minute budget
CHARS_PER_TOKEN = 3.5


class LLMUnavailable(Exception):
    """No provider could answer (all failed, or the call budget is used up)."""


class _Skip(Exception):
    """This provider can't serve this run; move to the next one."""


class _Retry(Exception):
    """Transient problem; try the same provider again."""


@dataclass(frozen=True)
class CallInfo:
    provider: str            # e.g. "groq:openai/gpt-oss-120b", or "cache"
    cached: bool
    seconds: float


def strict_schema(model: type[BaseModel]) -> dict:
    """pydantic JSON schema -> the strict form Groq requires: every object closed, every property required."""
    schema = model.model_json_schema()

    def fix(node: Any) -> None:
        if isinstance(node, dict):
            node.pop("title", None)
            node.pop("default", None)
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"])
            for v in node.values():
                fix(v)
        elif isinstance(node, list):
            for v in node:
                fix(v)

    fix(schema)
    return schema


def _short(text: str, n: int = 160) -> str:
    return " ".join(str(text).split())[:n]


class _Pacer:
    """Sliding one-minute token budget per model, so we wait a little instead of hitting a 429.
    Thread-safe: parallel batches reserve their share before calling."""
    def __init__(self, budget: int):
        self.budget, self.used = budget, []            # [[time, tokens]]
        self.lock = threading.Lock()

    def wait(self, need: int) -> list:
        """Blocks until `need` tokens fit in the last minute, then reserves them. Returns the reservation."""
        need = min(need, self.budget)
        for _ in range(4):                             # bounded: never spins forever
            with self.lock:
                now = time.monotonic()
                self.used = [u for u in self.used if now - u[0] < 60]
                total = sum(u[1] for u in self.used)
                if total + need <= self.budget or not self.used:
                    slot = [now, need]
                    self.used.append(slot)
                    return slot
                free, pause = total + need - self.budget, 0.0
                for t, n in self.used:
                    free -= n
                    if free <= 0:
                        pause = max(0.0, 60 - (now - t)) + 0.2
                        break
            step("ai", f"pausing {pause:.0f}s to stay under the Groq per-minute limit")
            time.sleep(pause)
        with self.lock:
            slot = [time.monotonic(), need]
            self.used.append(slot)
            return slot

    def spend(self, tokens: int, slot: list | None = None) -> None:
        """Replace a reservation with the real usage (or record usage without one)."""
        with self.lock:
            if slot is not None and slot in self.used:
                slot[1] = tokens
            else:
                self.used.append([time.monotonic(), tokens])


_PACERS: dict[str, _Pacer] = {}


class GroqProvider:
    def __init__(self, model: str, transport: httpx.BaseTransport | None = None):
        self.name, self.model, self.transport = f"groq:{model}", model, transport
        # gpt-oss always reasons (keep it low); Qwen 3.x on Groq accepts "none" = no reasoning tokens at all
        self.effort = "low" if model.startswith("openai/gpt-oss") else ("none" if model.startswith("qwen/qwen3") else None)
        self.pacer = _PACERS.setdefault(model, _Pacer(GROQ_TPM))   # shared by every client in this process

    def call(self, system: str, user: str, schema: type[M]) -> M:
        key = os.environ.get("GROQ_API_KEY")
        if not key:
            raise _Skip("GROQ_API_KEY is not set")
        body: dict[str, Any] = {
            "model": self.model, "temperature": 0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": schema.__name__.lower(), "strict": True, "schema": strict_schema(schema)}}}
        body["max_completion_tokens"] = GROQ_MAX_OUT
        if self.effort:
            body["reasoning_effort"] = self.effort
        guess = int((len(system) + len(user)) / CHARS_PER_TOKEN) + (1500 if self.effort == "low" else 700)
        slot = self.pacer.wait(guess)
        try:
            with httpx.Client(base_url=GROQ_BASE, timeout=TIMEOUT_S, transport=self.transport,
                              headers={"Authorization": f"Bearer {key}"}) as c:
                r = c.post("/chat/completions", json=body)
        except httpx.TimeoutException as e:
            raise _Retry("timed out") from e
        except httpx.HTTPError as e:
            raise _Retry(f"network error ({type(e).__name__})") from e
        try:
            used = int(r.json().get("usage", {}).get("total_tokens") or guess) if r.status_code == 200 else guess
        except (ValueError, AttributeError, TypeError):
            used = guess
        self.pacer.spend(used, slot)
        if r.status_code == 200:
            try:
                return schema.model_validate_json(r.json()["choices"][0]["message"]["content"])
            except (KeyError, IndexError, TypeError, ValueError, ValidationError) as e:
                raise _Retry(f"answer did not match the schema ({type(e).__name__})") from e
        text = _short(r.text)
        if r.status_code == 400 and self.effort and "reasoning" in text.lower():
            self.effort = None
            raise _Retry("model does not accept reasoning_effort")
        if r.status_code in (401, 403):
            raise _Skip(f"key rejected (HTTP {r.status_code})")
        if r.status_code == 404:
            raise _Skip("model not available on this key")
        if r.status_code == 429:
            try:
                wait = float(r.headers.get("retry-after") or 30)
            except ValueError:
                wait = 30.0
            if "per day" not in text.lower() and wait <= SHORT_WAIT_MAX_S:
                time.sleep(wait + 0.5)
                raise _Retry(f"rate limited for {wait:.0f}s")
            raise _Skip(f"rate limited: {text}")
        if r.status_code >= 500:
            raise _Retry(f"server error HTTP {r.status_code}")
        raise _Retry(f"HTTP {r.status_code}: {text}")


class GeminiProvider:
    def __init__(self, model: str, client_factory: Callable[[], Any] | None = None):
        self.name, self.model, self.factory = f"gemini:{model}", model, client_factory
        self.thinking_ok = True

    def call(self, system: str, user: str, schema: type[M]) -> M:
        if not os.environ.get("GEMINI_API_KEY"):
            raise _Skip("GEMINI_API_KEY is not set")
        from google import genai
        from google.genai import types

        client = self.factory() if self.factory else genai.Client(http_options=types.HttpOptions(timeout=TIMEOUT_S * 1000))
        cfg = types.GenerateContentConfig(
            system_instruction=system, temperature=0, response_mime_type="application/json", response_schema=schema,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            thinking_config=types.ThinkingConfig(thinking_level="LOW") if self.thinking_ok else None)
        try:
            res = client.models.generate_content(model=self.model, contents=user, config=cfg)
        except Exception as e:  # noqa: BLE001 - SDK raises many types; classified below
            msg = str(e)
            if self.thinking_ok and "thinking" in msg.lower() and ("400" in msg or "INVALID" in msg.upper()):
                self.thinking_ok = False
                raise _Retry("model does not accept the thinking setting") from e
            if any(s in msg for s in ("401", "403", "404", "NOT_FOUND", "PERMISSION_DENIED", "API_KEY")):
                raise _Skip(f"not usable: {_short(msg)}") from e
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                raise _Skip(f"quota: {_short(msg)}") from e
            raise _Retry(f"{type(e).__name__}: {_short(msg)}") from e
        parsed = getattr(res, "parsed", None)
        try:
            return parsed if isinstance(parsed, schema) else schema.model_validate_json(res.text)
        except (ValidationError, ValueError, TypeError) as e:
            raise _Retry(f"answer did not match the schema ({type(e).__name__})") from e


def parse_chain(chain: str, transport: httpx.BaseTransport | None = None,
                gemini_factory: Callable[[], Any] | None = None) -> list:
    providers = []
    for part in (p.strip() for p in chain.split(",") if p.strip()):
        kind, _, model = part.partition(":")
        if kind == "groq" and model:
            providers.append(GroqProvider(model, transport))
        elif kind == "gemini" and model:
            providers.append(GeminiProvider(model, gemini_factory))
        else:
            raise ValueError(f"bad provider entry {part!r}; use groq:<model> or gemini:<model>")
    return providers


@dataclass
class LLMClient:
    providers: list
    cache_dir: Path | None = None
    max_calls: int = 60
    calls: int = 0
    skipped: dict = field(default_factory=dict)     # provider name -> why it was dropped this run
    log: list = field(default_factory=list)         # (provider, outcome) per attempt, for the audit trail
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @classmethod
    def from_settings(cls, settings, transport=None, gemini_factory=None) -> "LLMClient":
        return cls(parse_chain(settings.llm_chain, transport, gemini_factory),
                   cache_dir=Path(settings.runs_dir) / "cache" / "llm", max_calls=settings.llm_max_calls)

    def _cache_path(self, task: str, system: str, user: str, schema: type[BaseModel]) -> Path | None:
        if not self.cache_dir:
            return None
        h = hashlib.sha256(json.dumps([task, system, user, schema.model_json_schema()], sort_keys=True).encode()).hexdigest()
        return self.cache_dir / f"{task}-{h[:32]}.json"

    def ask(self, task: str, system: str, user: str, schema: type[M], max_tries_each: int = 3,
            start: int = 0) -> tuple[M, CallInfo]:
        """start rotates which provider is tried first, so batches can share several per-model rate limits."""
        t0 = time.perf_counter()
        path = self._cache_path(task, system, user, schema)
        if path and path.is_file():
            try:
                stored = json.loads(path.read_text())
                return schema.model_validate(stored["output"]), CallInfo("cache", True, 0.0)
            except (OSError, ValueError, KeyError, ValidationError):
                pass                                            # bad cache entry: ignore, ask again
        n = len(self.providers)
        order = self.providers[start % n:] + self.providers[:start % n] if n else []
        for p in order:
            if p.name in self.skipped:
                continue
            tries = 0
            while tries < max_tries_each:
                with self._lock:                         # batches may run in parallel threads
                    if self.calls >= self.max_calls:
                        raise LLMUnavailable(f"call budget of {self.max_calls} used up")
                    self.calls += 1
                try:
                    out = p.call(system, user, schema)
                except _Skip as e:
                    self.skipped[p.name] = str(e)
                    self.log.append((p.name, f"skipped: {e}"))
                    step("ai", f"{p.name} skipped: {str(e)[:120]}")
                    break
                except _Retry as e:
                    tries += 1
                    self.log.append((p.name, f"retry: {e}"))
                    step("ai", f"{p.name} retry {tries}: {str(e)[:120]}")
                    continue
                self.log.append((p.name, "ok"))
                if path:
                    self._save(path, {"provider": p.name, "output": out.model_dump(mode="json")})
                return out, CallInfo(p.name, False, round(time.perf_counter() - t0, 2))
            else:
                self.skipped[p.name] = f"failed {max_tries_each} times"
        raise LLMUnavailable("no provider could answer: " + "; ".join(f"{k}: {v}" for k, v in self.skipped.items())[:400])

    @staticmethod
    def _save(path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w") as fh:
            json.dump(data, fh)
        os.replace(tmp, path)
