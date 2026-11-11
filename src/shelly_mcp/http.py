"""Streamable-HTTP entry point with a static bearer token, for running as a service.

``shelly-mcp`` (stdio) stays the default. ``shelly-mcp-http`` serves the same tools at
``/mcp`` for a reverse proxy or a container:

* ``SHELLY_MCP_TOKEN`` (required): clients must send ``Authorization: Bearer <token>``.
  Set ``SHELLY_MCP_ALLOW_NO_AUTH=1`` to run without one (trusted LAN only).
* ``SHELLY_MCP_HOST`` / ``SHELLY_MCP_PORT``: bind address (default ``0.0.0.0:8765``).
* ``GET /healthz`` is unauthenticated and returns ``ok``.
"""

from __future__ import annotations

import hmac
import os
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

import uvicorn

from shelly_mcp.server import mcp

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


async def _plain(send: Send, status: int, body: bytes, extra: list[tuple[bytes, bytes]]) -> None:
    headers = [(b"content-type", b"text/plain"), *extra]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


def bearer_guard(app: ASGIApp, token: str | None) -> ASGIApp:
    """Wrap ``app`` so every HTTP request except ``/healthz`` needs the bearer token."""
    expected = f"Bearer {token}".encode() if token else None

    async def guarded(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await app(scope, receive, send)
            return
        if scope.get("path") == "/healthz":
            await _plain(send, 200, b"ok", [])
            return
        if expected is not None:
            got = dict(scope.get("headers") or []).get(b"authorization", b"")
            if not hmac.compare_digest(got, expected):
                await _plain(send, 401, b"unauthorized", [(b"www-authenticate", b"Bearer")])
                return
        await app(scope, receive, send)

    return guarded


def build_app(token: str | None) -> ASGIApp:
    inner: Any = mcp.http_app(path="/mcp", stateless_http=True)
    # Non-HTTP scopes (lifespan) pass straight through, so FastMCP's startup still runs.
    return bearer_guard(inner, token)


def main() -> None:
    token = os.environ.get("SHELLY_MCP_TOKEN") or None
    if token is None and os.environ.get("SHELLY_MCP_ALLOW_NO_AUTH") != "1":
        raise SystemExit("SHELLY_MCP_TOKEN is not set (or set SHELLY_MCP_ALLOW_NO_AUTH=1)")
    host = os.environ.get("SHELLY_MCP_HOST", "0.0.0.0")  # noqa: S104 - container bind
    port = int(os.environ.get("SHELLY_MCP_PORT", "8765"))
    uvicorn.run(build_app(token), host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
