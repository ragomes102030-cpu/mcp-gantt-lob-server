import json
from pathlib import Path


def test_vercel_rewrites_keep_public_private_and_health_routes():
    config = json.loads((Path(__file__).parents[1] / "vercel.json").read_text(encoding="utf-8"))
    routes = {entry["source"]: entry["destination"] for entry in config["rewrites"]}

    assert routes["/public-mcp"] == "/api/public_mcp"
    assert routes["/mcp"] == "/api/index?__vercel_original_path=/mcp"
    assert routes["/healthz"] == "/api/index?__vercel_original_path=/healthz"
    assert routes["/api/healthz"] == "/api/index?__vercel_original_path=/api/healthz"
