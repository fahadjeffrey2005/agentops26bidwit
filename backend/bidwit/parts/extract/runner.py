"""Starts worker.py in a separate process with a time limit (and a memory cap where the OS allows)."""
from __future__ import annotations

import json
import subprocess  # nosec B404
import sys
from pathlib import Path

from bidwit.core.contracts import Rejected

WORKER = Path(__file__).with_name("worker.py")
GATE_TIMEOUT_S = 30
READ_TIMEOUT_BASE_S = 20
READ_TIMEOUT_PER_PAGE_S = 1.5
READ_TIMEOUT_MAX_S = 300


def _run(args: list[str], timeout: float) -> dict:
    try:
        # fixed argument list, no shell, isolated interpreter (-I): nothing from the file reaches a command line
        proc = subprocess.run(  # nosec B603
            [sys.executable, "-I", str(WORKER), *args],
            capture_output=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise Rejected(f"reading the PDF took longer than {int(timeout)}s; file refused") from e
    if proc.returncode != 0:
        raise Rejected(f"the PDF reader failed on this file (exit {proc.returncode}); file refused")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise Rejected("the PDF reader returned unreadable output; file refused") from e


def check(path: Path, max_pages: int) -> int:
    """Safety gate. Returns the page count or raises Rejected with a human-readable reason."""
    res = _run(["gate", str(path), str(max_pages)], GATE_TIMEOUT_S)
    if not res.get("ok"):
        raise Rejected(str(res.get("reason") or "file refused"))
    return int(res["pages"])


def read(path: Path, pages: int) -> list[dict]:
    timeout = min(READ_TIMEOUT_MAX_S, READ_TIMEOUT_BASE_S + READ_TIMEOUT_PER_PAGE_S * pages)
    return list(_run(["read", str(path)], timeout)["pages"])
