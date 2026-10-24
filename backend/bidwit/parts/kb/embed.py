"""Meaning vectors from Gemini, with an on-disk cache.

Any failure (no key, quota, network, bad response) raises EmbedError; the caller then
falls back to keyword-only search and records why. The API key is read by the SDK from the
GEMINI_API_KEY environment variable; it is never passed through or stored by this code.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Protocol

MODEL = "gemini-embedding-001"
DIM = 768                 # truncated from 3072 (the model supports shorter outputs); vectors re-normalised below
BATCH = 50
TIMEOUT_MS = 20_000


class EmbedError(Exception):
    pass


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str], task: str) -> list[list[float]]: ...


def _unit(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v))
    if not n or any(math.isnan(x) or math.isinf(x) for x in v):
        raise EmbedError("embedding is empty or not finite")
    return [x / n for x in v]


class GeminiEmbedder:
    name = f"{MODEL}/{DIM}"
    dim = DIM

    def __init__(self) -> None:
        if not os.environ.get("GEMINI_API_KEY"):
            raise EmbedError("GEMINI_API_KEY is not set")
        try:
            from google import genai
            from google.genai import types
        except ImportError as e:                         # pragma: no cover
            raise EmbedError("google-genai is not installed") from e
        self._types = types
        self._client = genai.Client(http_options=types.HttpOptions(timeout=TIMEOUT_MS))

    def embed(self, texts: list[str], task: str) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), BATCH):
            chunk = texts[i:i + BATCH]
            try:
                res = self._client.models.embed_content(
                    model=MODEL, contents=chunk,
                    config=self._types.EmbedContentConfig(task_type=task, output_dimensionality=DIM))
            except Exception as e:  # noqa: BLE001 - any API failure means: fall back
                raise EmbedError(f"Gemini embedding call failed ({type(e).__name__})") from e
            vecs = [list(e.values or []) for e in (res.embeddings or [])]
            if len(vecs) != len(chunk) or any(len(v) != DIM for v in vecs):
                raise EmbedError("Gemini returned the wrong number or size of embeddings")
            out += [_unit(v) for v in vecs]
        return out


class CachedEmbedder:
    """Wraps an embedder; vectors are stored by hash of (model, task, text). Text itself is not stored."""

    def __init__(self, inner: Embedder, cache_file: Path):
        self.inner, self.file, self.name, self.dim = inner, cache_file, inner.name, inner.dim
        try:
            self.cache: dict[str, list[float]] = json.loads(cache_file.read_text()) if cache_file.is_file() else {}
        except (OSError, json.JSONDecodeError):
            self.cache = {}                              # a corrupt cache is ignored, not trusted

    def _key(self, text: str, task: str) -> str:
        return hashlib.sha256(f"{self.name}|{task}|{text}".encode()).hexdigest()

    def embed(self, texts: list[str], task: str) -> list[list[float]]:
        keys = [self._key(t, task) for t in texts]
        todo = [t for t, k in zip(texts, keys) if not self._valid(self.cache.get(k))]
        if todo:
            for t, v in zip(todo, self.inner.embed(todo, task)):
                self.cache[self._key(t, task)] = v
            self._save()
        return [self.cache[k] for k in keys]

    def _valid(self, v) -> bool:
        """A cached vector is used only if it has the right size and only finite numbers."""
        return (isinstance(v, list) and len(v) == self.dim
                and all(isinstance(x, (int, float)) and math.isfinite(x) for x in v))

    def _save(self) -> None:
        self.file.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.file.parent, suffix=".tmp")
        with os.fdopen(fd, "w") as fh:
            json.dump(self.cache, fh)
        os.replace(tmp, self.file)                       # atomic: never a half-written cache
