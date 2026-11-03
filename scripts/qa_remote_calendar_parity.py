"""Remote stateless MCP smoke: discover tools and compare CPM x resource leveling calendar.

Both endpoints are public. Uses synthetic values and no secrets/project data.
Run only against approved hosts, with a bounded timeout.
"""
import asyncio
import json
import os

from fastmcp import Client

CRONOGRAMA = os.getenv(
    "QA_CRONOGRAMA_MCP_URL", "https://arquimedes-mcp-cronograma.vercel.app/public-mcp"
)
LOB = os.getenv(
    "QA_GANTT_LOB_MCP_URL", "https://arquimedes-mcp-gantt-lob.vercel.app/mcp"
)


def parse(result):
    if getattr(result, "is_error", False) or getattr(result, "isError", False):
        raise AssertionError(f"Remote MCP reported error: {result}")
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        if "result" in structured and isinstance(structured["result"], dict):
            return structured["result"]
        return structured
    data = getattr(result, "data", None)
    if isinstance(data, dict):
        return data
    for block in getattr(result, "content", []):
        if getattr(block, "type", None) == "text":
            obj = json.loads(block.text)
            if isinstance(obj, dict):
                return obj
    raise AssertionError("Remote tool response did not contain a JSON object")


async def main():
    expected_calendar = {
        "modo": "uteis", "calendar_id": "qa-common-2026-11",
        "dias_semana": [0, 1, 2, 3, 4],
        "feriados": ["2026-11-09"],
    }
    cpm_activities = [
        {"id": "A", "duracao_dias": 2},
        {"id": "B", "duracao_dias": 2},
    ]
    dependencies = [
        {"predecessora_id": "A", "sucessora_id": "B", "tipo": "TI", "lag_dias": 0}
    ]
    leveling_activities = [
        {"id": "A", "duracao_dias": 2, "recursos": {"equipe": 1}},
        {"id": "B", "duracao_dias": 2, "recursos": {"equipe": 1}},
    ]
    async with Client(CRONOGRAMA, timeout=30) as cpm_client:
        cpm_names = {getattr(t, "name", "") for t in await cpm_client.list_tools()}
        assert "calcular_cpm_com_calendario" in cpm_names, cpm_names
        cpm = parse(await cpm_client.call_tool(
            "calcular_cpm_com_calendario",
            {"atividades": cpm_activities, "dependencias": dependencies,
             "data_inicio": "2026-11-06", "calendario": expected_calendar}
        ))
    async with Client(LOB, timeout=30) as lob_client:
        lob_names = {getattr(t, "name", "") for t in await lob_client.list_tools()}
        assert "nivelar_recursos_com_calendario" in lob_names, lob_names
        assert "comparar_cenarios_custo_prazo" in lob_names, lob_names
        leveled = parse(await lob_client.call_tool(
            "nivelar_recursos_com_calendario",
            {"atividades": leveling_activities, "capacidades": {"equipe": 1},
             "dependencias": dependencies, "data_inicio": "2026-11-06",
             "calendario": expected_calendar}
        ))
        costs = parse(await lob_client.call_tool(
            "comparar_cenarios_custo_prazo",
            {"atividades": leveling_activities,
             "cenarios": [{"nome": "base", "capacidades": {"equipe": 1}}],
             "custos_por_recurso_dia": {"equipe": 100},
             "custo_indireto_por_dia": 50,
             "dependencias": dependencies,
             "data_inicio": "2026-11-06",
             "calendario": expected_calendar}
        ))
    assert cpm["persistido"] is False and leveled["persistido"] is False and costs["persistido"] is False
    assert cpm["duracao_projeto_dias"] == leveled["duracao_total_dias"] == 4
    cpm_byid = {a["id"]: a for a in cpm["atividades"]}
    lob_byid = {a["id"]: a for a in leveled["tarefas"]}
    for key in ("A", "B"):
        for field in ("data_inicio", "data_fim_exclusiva"):
            assert cpm_byid[key][field] == lob_byid[key][field], (key, field, cpm_byid[key], lob_byid[key])
    assert cpm["data_fim_projeto_exclusiva"] == "2026-11-13"
    assert costs["cenarios"][0]["custo_direto"] == 400
    assert costs["cenarios"][0]["custo_indireto"] == 200
    assert costs["cenarios"][0]["custo_total"] == 600
    print(json.dumps({
        "valid": True, "remote_cpm_tools": len(cpm_names),
        "remote_lob_tools": len(lob_names), "duration_days": 4,
        "calendar_id": expected_calendar["calendar_id"],
        "start": "2026-11-06", "exclusive_finish": "2026-11-13",
        "total_cost_synthetic": 600, "persistence": False
    }))


if __name__ == "__main__":
    asyncio.run(main())
