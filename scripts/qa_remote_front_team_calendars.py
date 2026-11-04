"""Remote production QA: physical fronts, individual team calendars and cost rates.

Uses only two synthetic tasks. Reads public tools via MCP protocol; no secrets.
"""
import asyncio
import json

from fastmcp import Client
from qa_remote_calendar_parity import LOB, parse


async def main():
    async with Client(LOB, timeout=30) as client:
        names = {tool.name for tool in await client.list_tools()}
        expected = {"nivelar_frentes_de_trabalho",
                    "nivelar_calendarios_por_equipe",
                    "comparar_cenarios_custo_prazo"}
        assert expected <= names, f"Missing public tools: {expected - names}"

        independent = [
            {"id": "A", "duracao_dias": 2, "local_id": "P01",
             "recursos": {"alvenaria": 1}},
            {"id": "B", "duracao_dias": 2, "local_id": "P01",
             "recursos": {"eletrica": 1}},
        ]
        fronts = parse(await client.call_tool(
            "nivelar_frentes_de_trabalho",
            {"atividades": independent,
             "capacidades_recursos": {"alvenaria": 1, "eletrica": 1},
             "capacidades_frentes": {"P01": 1}}
        ))
        assert fronts["persistido"] is False
        assert fronts["duracao_total_dias"] == 4
        assert [task["inicio_dia"] for task in fronts["tarefas"]] == [0, 2]
        assert all(task["local_id"] == "P01" for task in fronts["tarefas"])

        parallel = [{**independent[0]}, {**independent[1], "local_id": "P02"}]
        different_floors = parse(await client.call_tool(
            "nivelar_frentes_de_trabalho",
            {"atividades": parallel,
             "capacidades_recursos": {"alvenaria": 1, "eletrica": 1},
             "capacidades_frentes": {"P01": 1, "P02": 1}}
        ))
        assert different_floors["duracao_total_dias"] == 2
        assert [task["inicio_dia"] for task in different_floors["tarefas"]] == [0, 0]

        calendars = parse(await client.call_tool(
            "nivelar_calendarios_por_equipe",
            {"atividades": parallel,
             "capacidades_recursos": {"alvenaria": 1, "eletrica": 1},
             "calendarios_recursos": {
                 "alvenaria": {"dias_semana": [0, 1, 2, 3, 4],
                               "feriados": ["2026-11-09"]},
                 "eletrica": {"dias_semana": [1, 2, 3, 4, 5]},
             },
             "data_inicio": "2026-11-06",
             "capacidades_frentes": {"P01": 1, "P02": 1}}
        ))
        assert calendars["persistido"] is False
        by_id = {item["id"]: item for item in calendars["tarefas"]}
        assert by_id["A"]["dias_produtivos"] == ["2026-11-06", "2026-11-10"]
        assert by_id["B"]["dias_produtivos"] == ["2026-11-06", "2026-11-07"]
        assert calendars["data_fim_projeto_exclusiva"] == "2026-11-11"

        costs = parse(await client.call_tool(
            "comparar_cenarios_custo_prazo",
            {"atividades": [
                {"id": "A", "duracao_dias": 2, "recursos": {"equipe": 1}},
                {"id": "B", "duracao_dias": 2, "recursos": {"equipe": 1}},
             ],
             "cenarios": [{"nome": "uma-equipe", "capacidades": {"equipe": 1}},
                          {"nome": "duas-equipes", "capacidades": {"equipe": 2}}],
             "custos_por_recurso_dia": {"equipe": 100},
             "custo_indireto_por_dia": 50,
             "custos_mobilizacao_por_recurso": {"equipe": 100},
             "custos_ociosidade_por_recurso_dia": {"equipe": 10},
             "dependencias": [
                 {"predecessora_id": "A", "sucessora_id": "B", "tipo": "TI"}
             ]}
        ))
        assert costs["persistido"] is False
        by_scenario = {x["nome"]: x for x in costs["cenarios"]}
        assert by_scenario["uma-equipe"]["custo_total"] == 700
        assert by_scenario["duas-equipes"]["custo_total"] == 840
        assert by_scenario["uma-equipe"]["custo_mobilizacao"] == 100
        assert by_scenario["duas-equipes"]["custo_mobilizacao"] == 200

    print(json.dumps({
        "valid": True, "public_tools": sorted(expected),
        "same_front_days": 4, "separate_floors_days": 2,
        "alvenaria_productive_dates": by_id["A"]["dias_produtivos"],
        "eletrica_productive_dates": by_id["B"]["dias_produtivos"],
        "exclusive_finish": calendars["data_fim_projeto_exclusiva"],
        "cost_one_team": by_scenario["uma-equipe"]["custo_total"],
        "cost_two_teams": by_scenario["duas-equipes"]["custo_total"],
        "persistence": False,
    }))


if __name__ == "__main__":
    asyncio.run(main())
