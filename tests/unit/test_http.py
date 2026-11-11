"""Bearer guard on the HTTP entry point."""

from __future__ import annotations

from typing import Any

from shelly_mcp.http import bearer_guard


async def _run(app: Any, path: str, headers: list[tuple[bytes, bytes]]) -> int:
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b""}

    async def send(msg: dict[str, Any]) -> None:
        sent.append(msg)

    await app({"type": "http", "path": path, "headers": headers}, receive, send)
    return int(sent[0]["status"])


async def _inner(scope: Any, receive: Any, send: Any) -> None:
    await send({"type": "http.response.start", "status": 204, "headers": []})
    await send({"type": "http.response.body", "body": b""})


async def test_guard_requires_token() -> None:
    app = bearer_guard(_inner, "tok")
    assert await _run(app, "/mcp", []) == 401
    assert await _run(app, "/mcp", [(b"authorization", b"Bearer nope")]) == 401
    assert await _run(app, "/mcp", [(b"authorization", b"Bearer tok")]) == 204


async def test_healthz_open() -> None:
    assert await _run(bearer_guard(_inner, "tok"), "/healthz", []) == 200


async def test_no_token_mode_passes() -> None:
    assert await _run(bearer_guard(_inner, None), "/mcp", []) == 204
