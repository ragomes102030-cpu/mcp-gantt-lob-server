"""Remote EAP -> duration -> CPM -> resource LOB -> cost interoperability QA.

Only synthetic data is submitted. No authenticated or persistent endpoints.
"""
import asyncio
import json
import os

from fastmcp import Client
from qa_remote_calendar_parity import parse, CRONOGRAMA, LOB

EAP = os.getenv("QA_EAP_MCP_URL",
                "https://arquimedes-mcp-eap.vercel.app/public-mcp")


async def main():
    calendar = {
        "modo": "uteis", "calendar_id": "qa-eap-cpm-lob-202611",
        "dias_semana": [0, 1, 2, 3, 4],
        "feriados": ["2026-11-09"],
    }
    nodes = [
        {"eap_id": "1", "nome": "Obra ficticia", "nivel": 1},
        {"eap_id": "1.1", "parent_id": "1", "nome": "Estrutura", "nivel": 2},
        {"eap_id": "1.2", "parent_id": "1", "nome": "Alvenaria", "nivel": 2},
    ]
    packages = [
        {"eap_id": "1.1", "quantidade": 60, "produtividade": 30,
         "unidade": "m2", "fonte": "Premissa sintetica QA",
         "responsavel": "Equipe A", "criterio_aceite": "Inspecao"},
        {"eap_id": "1.2", "quantidade": 60, "produtividade": 30,
         "unidade": "m2", "fonte": "Premissa sintetica QA",
         "responsavel": "Equipe B", "criterio_aceite": "Inspecao"},
    ]
    async with Client(EAP, timeout=30) as client:
        names = {tool.name for tool in await client.list_tools()}
        assert {"validar_estrutura_eap", "avaliar_evidencia_eap"} <= names, names
        structure = parse(await client.call_tool("validar_estrutura_eap", {"nos": nodes}))
        evidence = parse(await client.call_tool("avaliar_evidencia_eap", {"itens": packages}))
    assert structure["ok"] is True and structure["total_nos"] == 3
    assert not structure["erros"] and structure["persistido"] is False
    assert evidence["persistido"] is False
    assert all(v["preenchidos"] == 2 for v in evidence["cobertura"].values())
    activity_ids = ["1.1", "1.2"]
    links = [{"predecessora_id": "1.1", "sucessora_id": "1.2",
              "tipo": "TI", "lag_dias": 0}]
    cpm_activities = []
    async with Client(CRONOGRAMA, timeout=30) as client:
        names_c = {tool.name for tool in await client.list_tools()}
        assert {"calcular_duracao_com_evidencia", "calcular_cpm_com_calendario"} <= names_c
        for package in packages:
            calc = parse(await client.call_tool(
                "calcular_duracao_com_evidencia",
                {"quantidade": package["quantidade"],
                 "produtividade": package["produtividade"],
                 "unidade": package["unidade"],
                 "unidade_produtividade": "m2/dia",
                 "fonte": package["fonte"]}
            ))
            assert calc["duracaoDias"] == 2 and calc["persistido"] is False
            cpm_activities.append({"id": package["eap_id"],
                                   "duracao_dias": calc["duracaoDias"]})
        cpm = parse(await client.call_tool(
            "calcular_cpm_com_calendario",
            {"atividades": cpm_activities, "dependencias": links,
             "data_inicio": "2026-11-06", "calendario": calendar}
        ))
    resources = [{"id": item["id"], "duracao_dias": item["duracao_dias"],
                  "recursos": {"equipe": 1}} for item in cpm_activities]
    async with Client(LOB, timeout=30) as client:
        names_l = {tool.name for tool in await client.list_tools()}
        assert {"nivelar_recursos_com_calendario", "comparar_cenarios_custo_prazo"} <= names_l
        lob = parse(await client.call_tool(
            "nivelar_recursos_com_calendario",
            {"atividades": resources, "capacidades": {"equipe": 1},
             "dependencias": links, "data_inicio": "2026-11-06",
             "calendario": calendar}
        ))
        costs = parse(await client.call_tool(
            "comparar_cenarios_custo_prazo",
            {"atividades": resources,
             "cenarios": [{"nome": "simulado", "capacidades": {"equipe": 1}}],
             "custos_por_recurso_dia": {"equipe": 100},
             "custo_indireto_por_dia": 50,
             "dependencias": links, "data_inicio": "2026-11-06",
             "calendario": calendar}
        ))
    assert all(x["persistido"] is False for x in (cpm, lob, costs))
    assert cpm["duracao_projeto_dias"] == lob["duracao_total_dias"] == 4
    by_cpm = {t["id"]: t for t in cpm["atividades"]}
    by_lob = {t["id"]: t for t in lob["tarefas"]}
    for id_ in activity_ids:
        for field in ("data_inicio", "data_fim_exclusiva"):
            assert by_cpm[id_][field] == by_lob[id_][field]
    assert cpm["data_fim_projeto_exclusiva"] == "2026-11-13"
    assert costs["cenarios"][0]["custo_total"] == 600
    print(json.dumps({
        "valid": True, "eap_nodes": 3, "packages": 2, "activities": 2,
        "links": 1, "cpm_lob_days": 4, "cpm_lob_differences": 0,
        "end_exclusive": "2026-11-13", "synthetic_cost": 600,
        "persistido": False
    }))


if __name__ == "__main__":
    asyncio.run(main())
