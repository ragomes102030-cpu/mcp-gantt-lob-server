"""Authenticated, stateless ASGI adapter for Vercel Python Functions.

Root app.py explicitly imports this entrypoint, so server.py stays available
for Render without triggering its SQLite startup side effects on Vercel.
"""
from __future__ import annotations

import hmac
import json
import os
from contextlib import AsyncExitStack

from public_mcp import public_app as _public_app

_REQUIRED_DB = ()
_MISSING = [key for key in ("MCP_API_TOKEN", *_REQUIRED_DB) if not os.environ.get(key)]
_mcp_app = None
_internal_lookup = None
if not _MISSING:
    from mcp_gantt_lob.server import mcp as _server
    _mcp_app = _server.http_app(path="/mcp", stateless_http=True, json_response=True)


async def _send_json(send, status, payload, *, challenge=False):
    data = json.dumps(payload).encode("utf-8")
    headers = [(b"content-type", b"application/json"), (b"cache-control", b"no-store")]
    if challenge:
        headers.append((b"www-authenticate", b'Bearer realm="mcp"'))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": data})


async def _empty_lifespan(receive, send):
    while True:
        event = await receive()
        if event["type"] == "lifespan.startup":
            await send({"type": "lifespan.startup.complete"})
        elif event["type"] == "lifespan.shutdown":
            await send({"type": "lifespan.shutdown.complete"})
            return


async def _lifespan_both(receive, send):
    """Start the public and private FastMCP session managers independently."""
    event = await receive()
    if event["type"] != "lifespan.startup":
        return
    try:
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(_public_app.router.lifespan_context(_public_app))
            if _mcp_app is not None:
                await stack.enter_async_context(_mcp_app.router.lifespan_context(_mcp_app))
            await send({"type": "lifespan.startup.complete"})
            while True:
                event = await receive()
                if event["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
    except Exception as exc:
        await send({"type": "lifespan.startup.failed", "message": str(exc)})


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        await _lifespan_both(receive, send)
        return
    if scope["type"] != "http":
        return
    path = scope.get("path", "")
    if path in ("/healthz", "/api/healthz"):
        configured = not bool(_MISSING)
        await _send_json(send, 200 if configured else 503, {"ok": configured, "configured": configured})
        return
    # Public endpoint has its OWN tools and no access to project storage.
    # Private /mcp and /internal/eap-node still require MCP_API_TOKEN.
    if path.rstrip("/") == "/public-mcp":
        # Claude may first probe the URL with an ordinary GET/HEAD before
        # negotiating MCP Streamable HTTP. Such probes need a stable success
        # status; real SSE GET and JSON-RPC POST continue to the MCP transport.
        method = scope.get("method", "GET")
        if method in ("GET", "HEAD") and b"text/event-stream" not in dict(
            (key.lower(), val) for key, val in scope.get("headers", [])
        ).get(b"accept", b""):
            if method == "HEAD":
                await send({"type": "http.response.start", "status": 200,
                            "headers": [(b"cache-control", b"no-store")]})
                await send({"type": "http.response.body", "body": b""})
            else:
                await _send_json(send, 200, {"ok": True,
                    "transport": "streamable-http", "endpoint": "/public-mcp",
                    "auth": "none", "capabilities": "stateless-calculations-only"})
            return
        if method == "OPTIONS":
            await send({"type": "http.response.start", "status": 204,
                        "headers": [(b"allow", b"GET, HEAD, POST, OPTIONS"),
                                    (b"cache-control", b"no-store")]})
            await send({"type": "http.response.body", "body": b""})
            return
        public_scope = dict(scope)
        public_scope["path"] = "/mcp"
        public_scope["raw_path"] = b"/mcp"
        await _public_app(public_scope, receive, send)
        return
    if path not in ("/mcp", "/api/index"):
        await _send_json(send, 404, {"ok": False, "error": "Not found"})
        return
    if _MISSING:
        await _send_json(send, 503, {"ok": False, "error": "MCP configuration incomplete"})
        return
    headers = {key.lower(): val for key, val in scope.get("headers", [])}
    expected = ("Bearer " + os.environ["MCP_API_TOKEN"]).encode("utf-8")
    if not hmac.compare_digest(headers.get(b"authorization", b""), expected):
        await _send_json(send, 401, {"ok": False, "error": "Authentication required"}, challenge=True)
        return

    mcp_scope = dict(scope)
    mcp_scope["path"] = "/mcp"
    mcp_scope["raw_path"] = b"/mcp"
    await _mcp_app(mcp_scope, receive, send)
