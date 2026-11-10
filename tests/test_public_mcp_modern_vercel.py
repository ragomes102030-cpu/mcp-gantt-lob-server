import json
from io import BytesIO
import threading
from types import SimpleNamespace
from http.server import HTTPServer
from urllib.request import Request, urlopen

import api.public_mcp as vercel_public_mcp
from api.public_mcp import _dispatch_modern_jsonrpc, _run_legacy_asgi, handler


def test_modern_discover_and_tools_list_are_supported():
    discover = _dispatch_modern_jsonrpc({"jsonrpc": "2.0", "id": 1,
                                         "method": "server/discover"})
    listed = _dispatch_modern_jsonrpc({"jsonrpc": "2.0", "id": 2,
                                       "method": "tools/list"})

    assert discover["id"] == 1
    assert "2026-07-28" in discover["result"]["supportedVersions"]
    assert listed["id"] == 2
    names = {tool["name"] for tool in listed["result"]["tools"]}
    assert "dimensionar_equipes_lob" in names
    assert "calcular_lob_com_vinculos" in names


def test_modern_tools_call_returns_structured_result_without_persisting():
    response = _dispatch_modern_jsonrpc({
        "jsonrpc": "2.0", "id": "call-1", "method": "tools/call",
        "params": {"name": "dimensionar_equipes_lob",
                   "arguments": {"tempo_unitario": 4, "ritmo_desejado": 2}},
    })

    result = response["result"]
    assert response["id"] == "call-1"
    assert result["isError"] is False
    assert result["structuredContent"] == {"numero_equipes": 2, "persistido": False}


def test_modern_http_post_frames_a_complete_chunk():
    request = {"jsonrpc": "2.0", "id": 7, "method": "server/discover"}
    instance = handler.__new__(handler)
    instance.headers = {"Content-Length": str(len(json.dumps(request).encode())),
                        "MCP-Protocol-Version": "2026-07-28"}
    instance.rfile = BytesIO(json.dumps(request).encode())
    instance.client_address = ("127.0.0.1", 40000)
    captured = {}

    def reply(status, body, headers=(), *, chunked=False):
        captured.update(status=status, body=body, headers=list(headers), chunked=chunked)

    instance._reply = reply
    instance.do_POST()

    assert captured["status"] == 200
    assert captured["chunked"] is True
    assert json.loads(captured["body"])["id"] == 7


def test_modern_rejects_mismatched_method_header():
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    instance = handler.__new__(handler)
    instance.headers = {"Content-Length": str(len(json.dumps(request).encode())),
                        "MCP-Protocol-Version": "2026-07-28",
                        "Mcp-Method": "tools/call"}
    instance.rfile = BytesIO(json.dumps(request).encode())
    instance.client_address = ("127.0.0.1", 40000)
    captured = {}

    def reply(status, body, headers=(), *, chunked=False):
        captured.update(status=status, body=body, chunked=chunked)

    instance._reply = reply
    instance.do_POST()

    assert captured["status"] == 400
    assert captured["chunked"] is False


def test_http_chunked_reply_writes_the_terminal_chunk():
    instance = handler.__new__(handler)
    instance.headers = {}
    instance.command = "POST"
    instance.wfile = BytesIO()
    sent_headers = []
    instance.send_response = lambda status: None
    instance.send_header = lambda key, value: sent_headers.append((key, value))
    instance.end_headers = lambda: None

    instance._reply(200, b'{"ok":true}', chunked=True)

    assert ("Transfer-Encoding", "chunked") in sent_headers
    assert instance.wfile.getvalue().endswith(b"\r\n0\r\n\r\n")


def test_fastmcp4_server_api_is_serialized(monkeypatch):
    class McpTool:
        def model_dump(self, **kwargs):
            return {"name": "fake_tool", "inputSchema": {"type": "object"}}

    class RegisteredTool:
        name = "fake_tool"

        def to_mcp_tool(self):
            return McpTool()

    class ToolResult:
        content = [SimpleNamespace(model_dump=lambda **kwargs: {
            "type": "text", "text": "ok"})]
        structured_content = {"ok": True, "persistido": False}
        is_error = False

    class ServerApi:
        async def list_tools(self):
            return [RegisteredTool()]

        async def call_tool(self, name, arguments):
            assert name == "fake_tool"
            assert arguments == {"x": 1}
            return ToolResult()

    monkeypatch.setattr(vercel_public_mcp, "public_mcp", ServerApi())
    listed = _dispatch_modern_jsonrpc({"jsonrpc": "2.0", "id": 3,
                                       "method": "tools/list"})
    called = _dispatch_modern_jsonrpc({"jsonrpc": "2.0", "id": 4,
                                       "method": "tools/call", "params": {
                                           "name": "fake_tool", "arguments": {"x": 1}}})

    assert listed["result"]["tools"] == [
        {"name": "fake_tool", "inputSchema": {"type": "object"}}
    ]
    assert called["result"]["structuredContent"] == {"ok": True, "persistido": False}


def test_modern_http_response_is_complete_for_a_real_http_client():
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        payload = {"jsonrpc": "2.0", "id": 8, "method": "server/discover",
                   "params": {"_meta": {
                       "io.modelcontextprotocol/protocolVersion": "2026-07-28"}}}
        request = Request(
            f"http://127.0.0.1:{server.server_port}/public-mcp",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json",
                     "Accept": "application/json, text/event-stream",
                     "MCP-Protocol-Version": "2026-07-28",
                     "Mcp-Method": "server/discover"},
            method="POST",
        )
        with urlopen(request, timeout=10) as response:
            result = json.loads(response.read())
            assert response.status == 200
            assert response.headers.get("Transfer-Encoding") == "chunked"
        assert "2026-07-28" in result["result"]["supportedVersions"]
        assert result["result"]["capabilities"] == {"tools": {}}
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_legacy_initialize_still_uses_fastmcp_asgi_transport():
    request = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-03-26", "capabilities": {},
        "clientInfo": {"name": "regression-test", "version": "1"},
    }}
    status, body, _headers = _run_legacy_asgi(
        "POST", "/public-mcp", b"", {
            "Host": "localhost", "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": "2025-03-26",
        }, json.dumps(request).encode(), ("127.0.0.1", 40000), ("localhost", 443), "https",
    )

    assert status == 200
    assert body
