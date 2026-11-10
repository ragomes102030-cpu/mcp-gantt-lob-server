"""Direct HTTP entry point for the stateless public MCP on Vercel.

Vercel's Python ASGI streaming adapter has returned an unterminated chunked
body for modern MCP JSON responses. This handler builds the modern response
before writing HTTP framing; legacy requests still use FastMCP's ASGI app.
"""
from __future__ import annotations

import asyncio
import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit

from mcp_public_origins import allowed_public_origins
from public_mcp import public_app, public_mcp

_CORS_HEADERS = [
    ("Access-Control-Allow-Methods", "POST, GET, HEAD, OPTIONS"),
    ("Access-Control-Allow-Headers", "Accept, Content-Type, MCP-Protocol-Version, Mcp-Method, Mcp-Name, Mcp-Session-Id, Last-Event-ID"),
    ("Access-Control-Expose-Headers", "MCP-Protocol-Version, Mcp-Session-Id"),
    ("Access-Control-Max-Age", "600"),
    ("Vary", "Origin"),
]


def _jsonable(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


async def _list_tools():
    # FastMCP 4 exposes list_tools on the server. Keep compatibility with the
    # older pinned-compatible tool manager API for local test environments.
    method = getattr(public_mcp, "list_tools", None)
    if method:
        return await method()
    tools = await public_mcp._tool_manager.get_tools()
    return list(tools.values()) if isinstance(tools, dict) else list(tools)


async def _call_tool(name, arguments):
    method = getattr(public_mcp, "call_tool", None)
    if method:
        return await method(name, arguments)
    tool = await public_mcp._tool_manager.get_tool(name)
    if tool is None:
        return None
    return await tool.run(arguments)


def _modern_tool_result(result):
    content = [_jsonable(item) for item in (getattr(result, "content", None) or [])]
    response = {"content": content, "isError": bool(getattr(result, "is_error", False))}
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        response["structuredContent"] = _jsonable(structured)
    return response


def _dispatch_modern_jsonrpc(request):
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}
    if not isinstance(params, dict):
        return {"jsonrpc": "2.0", "id": request_id,
                "error": {"code": -32602, "message": "params must be an object"}}

    if method == "server/discover":
        return {"jsonrpc": "2.0", "id": request_id, "result": {
            "cacheScope": "private",
            "capabilities": {"tools": {}},
            "instructions": ("Modo publico de calculo LOB. Analisa somente os dados "
                             "enviados na chamada, sem consultar ou alterar obras e baselines."),
            "resultType": "complete", "supportedVersions": ["2026-07-28"],
            "ttlMs": 0,
            "_meta": {"io.modelcontextprotocol/serverInfo":
                      {"name": "arquimedes-gantt-lob-publico", "version": ""}},
        }}

    if method == "tools/list":
        listed = asyncio.run(_list_tools())
        tools = []
        for tool in listed:
            if hasattr(tool, "to_mcp_tool"):
                item = _jsonable(tool.to_mcp_tool())
            else:
                item = {"name": tool.name, "inputSchema": _jsonable(tool.parameters)}
                if getattr(tool, "description", None):
                    item["description"] = tool.description
                if getattr(tool, "annotations", None) is not None:
                    item["annotations"] = _jsonable(tool.annotations)
            tools.append(item)
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": tools}}

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return {"jsonrpc": "2.0", "id": request_id,
                    "error": {"code": -32602, "message": "invalid tool name or arguments"}}
        try:
            result = asyncio.run(_call_tool(name, arguments))
            if result is None:
                return {"jsonrpc": "2.0", "id": request_id,
                        "error": {"code": -32602, "message": "Unknown tool"}}
            call_result = _modern_tool_result(result)
        except Exception as exc:
            # Match FastMCP's masked public errors; do not return stack details.
            call_result = {"content": [{"type": "text", "text": str(exc)}],
                           "structuredContent": {"erro": str(exc), "persistido": False},
                           "isError": True}
        return {"jsonrpc": "2.0", "id": request_id, "result": call_result}

    return {"jsonrpc": "2.0", "id": request_id,
            "error": {"code": -32601, "message": "Method not found"}}


def _run_legacy_asgi(method, path, query, headers, body, client, server, scheme):
    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
             "http_version": "1.1", "method": method, "scheme": scheme,
             "path": "/mcp", "raw_path": b"/mcp", "query_string": query,
             "root_path": path,
             "headers": [(k.lower().encode("latin-1"), v.encode("latin-1"))
                         for k, v in headers.items()],
             "server": server, "client": client}
    received = False
    messages = []

    async def receive():
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    async def dispatch():
        async with public_app.router.lifespan_context(public_app):
            await public_app(scope, receive, send)

    asyncio.run(dispatch())
    start = next((message for message in messages
                  if message["type"] == "http.response.start"), None)
    if start is None:
        raise RuntimeError("Public MCP did not start an HTTP response")
    response_body = b"".join(message.get("body", b"") for message in messages
                              if message["type"] == "http.response.body")
    response_headers = [(key.decode("latin-1"), value.decode("latin-1"))
                        for key, value in start.get("headers", [])]
    return start["status"], response_body, response_headers


class handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        if "text/event-stream" in self.headers.get("Accept", ""):
            self._reply(405, b"", [("Allow", "POST, OPTIONS"), ("Cache-Control", "no-store")])
            return
        payload = {"ok": True, "transport": "streamable-http", "endpoint": "/public-mcp",
                   "auth": "none", "capabilities": "stateless-calculations-only"}
        self._reply(200, json.dumps(payload).encode(),
                    [("Content-Type", "application/json"), ("Cache-Control", "no-store")])

    def do_HEAD(self):
        self._reply(200, b"", [("Cache-Control", "no-store")])

    def do_OPTIONS(self):
        self._reply(204, b"", [("Allow", "GET, HEAD, POST, OPTIONS")])

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._reply(400, b"Invalid Content-Length", [("Content-Type", "text/plain")])
            return
        if length <= 0:
            self._reply(400, b"Request body required", [("Content-Type", "text/plain")])
            return
        body = self.rfile.read(length)
        if len(body) != length:
            self._reply(400, b"Incomplete request body", [("Content-Type", "text/plain")])
            return
        try:
            protocol_version = self.headers.get("MCP-Protocol-Version", "")
            if protocol_version == "2026-07-28":
                request = json.loads(body)
                if not isinstance(request, dict):
                    raise ValueError("JSON-RPC request must be an object")
                if not isinstance(request.get("params") or {}, dict):
                    raise ValueError("JSON-RPC params must be an object")
                method_header = self.headers.get("Mcp-Method")
                if method_header and method_header != request.get("method"):
                    raise ValueError("Mcp-Method does not match JSON-RPC method")
                tool_header = self.headers.get("Mcp-Name")
                request_name = (request.get("params") or {}).get("name")
                if tool_header and tool_header != request_name:
                    raise ValueError("Mcp-Name does not match JSON-RPC tool name")
                response = _dispatch_modern_jsonrpc(request)
                self._reply(200, json.dumps(response, ensure_ascii=False).encode(),
                            [("Content-Type", "application/json"), ("Cache-Control", "no-store")],
                            chunked=True)
                return

            host = self.headers.get("Host", "localhost")
            parsed_host = urlsplit("//" + host)
            scheme = self.headers.get("X-Forwarded-Proto", "https").split(",", 1)[0].strip()
            path, _, query = self.path.partition("?")
            status, response_body, response_headers = _run_legacy_asgi(
                "POST", path, query.encode("latin-1"), self.headers, body,
                self.client_address,
                (parsed_host.hostname or "localhost", parsed_host.port or 443), scheme,
            )
        except (ValueError, json.JSONDecodeError):
            self._reply(400, b"Invalid MCP request", [("Content-Type", "text/plain")])
            return
        except Exception:
            self._reply(500, b"Public MCP request failed", [("Content-Type", "text/plain")])
            return
        self._reply(status, response_body, response_headers)

    def _reply(self, status, body, headers=(), *, chunked=False):
        origin = self.headers.get("Origin", "")
        allowed = allowed_public_origins()
        if origin and origin.lower() not in allowed:
            status = 403
            body = json.dumps({"ok": False, "error": "Origin not allowed"}).encode()
            headers = [("Content-Type", "application/json"), ("Cache-Control", "no-store")]
            chunked = False
        response_headers = [(key, value) for key, value in headers
                            if key.lower() not in ("content-length", "transfer-encoding", "connection")]
        if origin and origin.lower() in allowed:
            response_headers.extend(_CORS_HEADERS)
            response_headers.append(("Access-Control-Allow-Origin", origin))
        self.send_response(status)
        for key, value in response_headers:
            self.send_header(key, value)
        if chunked:
            self.send_header("Transfer-Encoding", "chunked")
        else:
            self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        if body and self.command != "HEAD":
            if chunked:
                self.wfile.write(f"{len(body):X}\r\n".encode("ascii") + body + b"\r\n0\r\n\r\n")
            else:
                self.wfile.write(body)
        self.close_connection = True

    def log_message(self, format, *args):
        return
