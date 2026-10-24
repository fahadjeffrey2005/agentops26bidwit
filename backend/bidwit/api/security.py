"""HTTP hardening for the local API, as one plain ASGI middleware (no extra dependencies).

1. Host check: only requests addressed to localhost names are served. Blocks DNS-rebinding, where a web page
   makes the browser talk to 127.0.0.1 under the attacker's own domain name.
2. CSRF: every POST must carry the header `X-BidWit: 1`. A web page from another origin can only add a custom
   header after a CORS preflight, which our CORS policy refuses, so it can't start runs or answer gates.
3. Body limits: POSTs must declare Content-Length; uploads are capped at the configured size + 1 MB of form
   overhead and everything else at 1 MB, before any byte is parsed or written to disk.
4. Security headers on every response (no sniffing, no framing, no referrer, no caching of run data).
"""
from __future__ import annotations

import json
import os

JSON_LIMIT = 1 << 20
FORM_OVERHEAD = 1 << 20
DEFAULT_HOSTS = "127.0.0.1,localhost,testserver"
HEADERS = [(b"x-content-type-options", b"nosniff"), (b"x-frame-options", b"DENY"),
           (b"referrer-policy", b"no-referrer"), (b"cache-control", b"no-store"),
           (b"cross-origin-resource-policy", b"same-origin")]
CSP = (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'")


class Hardening:
    def __init__(self, app, max_upload_mb: int):
        self.app = app
        self.upload_limit = max_upload_mb * (1 << 20) + FORM_OVERHEAD
        self.hosts = {h.strip().lower() for h in os.environ.get("BIDWIT_ALLOWED_HOSTS", DEFAULT_HOSTS).split(",") if h.strip()}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        host = headers.get("host", "").rsplit(":", 1)[0].strip("[]").lower()
        if host not in self.hosts:
            return await _reject(send, 421, "unknown host")
        if scope["method"] == "POST":
            if headers.get("x-bidwit") != "1":
                return await _reject(send, 403, "missing X-BidWit header")
            try:
                size = int(headers["content-length"])
            except (KeyError, ValueError):
                return await _reject(send, 411, "Content-Length required")
            limit = self.upload_limit if headers.get("content-type", "").startswith("multipart/") else JSON_LIMIT
            if size < 0 or size > limit:
                return await _reject(send, 413, f"request body larger than {limit // (1 << 20)} MB")
        docs = scope["path"].startswith("/api/docs")

        async def send_hardened(msg):
            if msg["type"] == "http.response.start":
                msg = {**msg, "headers": list(msg.get("headers", [])) + HEADERS + ([] if docs else [CSP])}
            await send(msg)
        return await self.app(scope, receive, send_hardened)


async def _reject(send, status: int, detail: str):
    body = json.dumps({"detail": detail}).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())] + HEADERS})
    await send({"type": "http.response.body", "body": body})
