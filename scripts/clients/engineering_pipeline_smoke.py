"""Cross-MCP fictitious engineering pipeline with explicit fail-closed semantics.

Public, stateless endpoints only. No database, private tools or real works.
XLSX is tested locally in tests/test_arquimedes_engineering_benchmark.py,
because gerar_gantt is private and must not be accessed anonymously.
"""
from __future__ import annotations
import asyncio
import json
import os
import sys
from mcp import Client

URLS = {
    "eap": os.getenv("EAP_PUBLIC_MCP_URL", "https://arquimedes-mcp-eap.vercel.app/public-mcp"),
    "cron": os.getenv("CRONOGRAMA_PUBLIC_MCP_URL", "https://arquimedes-mcp-cronograma.vercel.app/public-mcp"),
    "lob": os.getenv("GANTT_LOB_PUBLIC_MCP_URL", "https://arquimedes-mcp-gantt-lob.vercel.app/public-mcp"),
}

def unpack(response):
    if response.is_error:
        raise RuntimeError("MCP retornou erro; calculo bloqueado")
    raw = response.structured_content
    if raw is None:
        raw = next((json.loads(item.text) for item in response.content
                    if item.type == "text"), None)
    if not isinstance(raw, dict):
        raise RuntimeError("MCP retornou resposta sem dados estruturados")
    return raw.get("result", raw)


async def tool(client, name, args):
    return unpack(await asyncio.wait_for(client.call_tool(name, args), timeout=15))


async def pipeline():
    # IDs stable and explicit in the local orchestration envelope.
    envelope = {"project_id":"FICTICIO-INTEGRACAO","schema_version":"1.0",
                "eap_uid":"stable-ficticio-001", "activity_id":"F01",
                "location_id":"P01","calendar_id":None}
    async with Client(URLS["eap"], mode="auto") as eap:
        assert {t.name for t in (await eap.list_tools()).tools} == {
            "avaliar_evidencia_eap", "validar_estrutura_eap"}
        r = await tool(eap, "validar_estrutura_eap", {"nos":[
            {"eap_id":"1","parent_id":None,"nivel":1},
            {"eap_id":"1.1","parent_id":"1","nivel":2},
            {"eap_id":"1.2","parent_id":"1","nivel":2}]})
    assert r["ok"] is True and r["total_nos"] == 3 and r["persistido"] is False
    async with Client(URLS["cron"], mode="auto") as cron:
        assert {t.name for t in (await cron.list_tools()).tools} == {
            "calcular_duracao_com_evidencia", "calcular_cpm_com_evidencia"}
        c = await tool(cron, "calcular_cpm_com_evidencia", {
            "atividades":[{"id":"F01","duracao_dias":2},{"id":"A01","duracao_dias":3}],
            "dependencias":[{"predecessora_id":"F01","sucessora_id":"A01","tipo":"TI","lag_dias":0}]})
    by_id = {x["id"]:x for x in c["atividades"]}
    assert c["duracao_projeto_dias"] == 5 and c["persistido"] is False
    assert by_id["F01"]["ES"] == 0 and by_id["A01"]["ES"] == 2
    assert set(c["caminho_critico"]) == {"F01","A01"}
    async with Client(URLS["lob"], mode="auto") as lob:
        lob_tools = {t.name for t in (await lob.list_tools()).tools}
        assert {"calcular_linha_balanco", "balancear_ritmos_lob",
                "dimensionar_equipes_lob", "listar_temas"}.issubset(lob_tools)
        l = await tool(lob, "calcular_linha_balanco", {
            "atividades":[{"nome":"Estrutura","tempo_unitario":2},
                          {"nome":"Alvenaria","tempo_unitario":3}],
            "unidades":["P01","P02"],"data_inicio":"2026-11-02"})
    assert l["persistido"] is False and l["duracao_total_dias"] == 8
    assert l["atividades"][0]["unidades"][0]["data_inicio"] == "2026-11-02"
    assert l["atividades"][1]["unidades"][1]["fim_dia"] == 8
    if "calcular_lob_com_vinculos" in lob_tools:
        # The new MCP tool remains independent and preserves identifiers.
        async with Client(URLS["lob"], mode="auto") as advanced:
            calculated = await tool(advanced,"calcular_lob_com_vinculos", {
                "atividades":[{"activity_id":"F01","eap_uid":envelope["eap_uid"],"duracao_dias":2},
                              {"activity_id":"A01","eap_uid":"stable-ficticio-002","duracao_dias":3}],
                "locais":["P01","P02"],
                "dependencias":[
                  {"predecessora_id":"F01","predecessora_local":"P01","sucessora_id":"A01","sucessora_local":"P01"},
                  {"predecessora_id":"F01","predecessora_local":"P02","sucessora_id":"A01","sucessora_local":"P02"}],
                "data_inicio":"2026-11-02"})
        assert calculated["duracao_total_dias"] == 8
        assert calculated["persistido"] is False
        assert any(x["eap_uid"]==envelope["eap_uid"] for x in calculated["tarefas"])
    return {"status":"PASSOU","verified_public_tool_count":4 + len(lob_tools),"scope_nodes":3,"cpm_days":5,"lob_days":8,
            "eap_uid":envelope["eap_uid"],"schema_version":"1.0",
            "warning":"Gantt XLSX privado validado em testes locais, nao via MCP publico"}


def main():
    try:
        if "--simulate-unavailable" in sys.argv:
            raise ConnectionError("MCP de teste artificialmente indisponivel")
        result = asyncio.run(asyncio.wait_for(pipeline(),timeout=75))
    except Exception as exc:
        print(json.dumps({"status":"BLOQUEADO","error_type":type(exc).__name__,
                          "reason":str(exc)[:250],"no_fallback_calculation":True},
                         ensure_ascii=False),flush=True)
        return 2
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
