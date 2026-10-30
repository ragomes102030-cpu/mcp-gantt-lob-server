"""External-client MCP interoperability regression, read-only.

Connects with the official Python SDK (legacy and modern) to three publicly
accessible MCP endpoints. This does not access or modify real works/projects.
"""
import asyncio
import json
import os
from mcp import Client

ENDPOINTS = {
    "eap": os.environ["EAP_PUBLIC_MCP_URL"],
    "cronograma": os.environ["CRONOGRAMA_PUBLIC_MCP_URL"],
    "gantt_lob": os.environ["GANTT_LOB_PUBLIC_MCP_URL"],
}
CASE = {
    "eap": ("validar_estrutura_eap",
            {"nos": [{"eap_id": "1", "parent_id": None, "nivel": 1}]}, "ok", True,
            {"avaliar_evidencia_eap", "validar_estrutura_eap"}),
    "cronograma": ("calcular_duracao_com_evidencia",
                   {"quantidade": 12, "produtividade": 3, "unidade": "m2",
                    "unidade_produtividade": "m2"}, "duracaoDias", 4,
                   {"calcular_duracao_com_evidencia", "calcular_cpm_com_evidencia"}),
    "gantt_lob": ("dimensionar_equipes_lob",
                  {"tempo_unitario": 6, "ritmo_desejado": 2}, "numero_equipes", 3,
                  {"balancear_ritmos_lob", "calcular_linha_balanco",
                   "dimensionar_equipes_lob", "listar_temas"}),
}


def decode(result):
    assert not result.is_error, f"MCP tool failed: {result}"
    if result.structured_content is not None:
        v = result.structured_content
        if isinstance(v, dict):
            return v.get("result", v)
        return v
    for item in result.content:
        if item.type == "text":
            v = json.loads(item.text)
            return v.get("result", v) if isinstance(v, dict) else v
    raise AssertionError("No structured result and no JSON text content")


async def check_server(name, mode):
    tool, args, field, expected, names = CASE[name]
    async with Client(ENDPOINTS[name], mode=mode) as client:
        actual_version = str(client.protocol_version)
        if mode == "auto":
            assert actual_version == "2026-07-28", (name, mode, actual_version)
        else:
            assert actual_version.startswith("2025-"), (name, mode, actual_version)
        listed = await client.list_tools()
        actual = {t.name for t in listed.tools}
        permitted = names | ({"calcular_lob_com_vinculos"} if name == "gantt_lob" else set())
        assert names <= actual <= permitted, (name, mode, actual, names, permitted)
        data = decode(await client.call_tool(tool, args))
        assert data[field] == expected, (name, mode, data)
        assert data.get("persistido") is False, (name, "Unexpected mutation response")
        print(json.dumps({"sdk": "mcp-python", "server": name,
                          "mode": mode, "negotiated": actual_version,
                          "tools": sorted(actual), "case": tool, "result": expected}),
              flush=True)


async def main():
    for name in ENDPOINTS:
        for mode in ("auto", "legacy"):
            await check_server(name, mode)


if __name__ == "__main__":
    asyncio.run(main())
