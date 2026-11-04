"""200 activity capacity boundary remote QA, 50 floors x 4 teams.

Independent per-day resource/front/holiday/dependency and cost audits.
Synthetic only. This exercises the documented 200 activity limit.
"""
import asyncio
import json

from fastmcp import Client
from qa_remote_calendar_parity import LOB, parse
from qa_remote_resource_front_stress import (
    TRADES, DATES, CALENDARS, RATES, IDLE, MOB, verify_schedule, independent_costs,
)


def activities_and_links():
    tasks, links = [], []
    for floor in range(1, 51):
        for index, resource in enumerate(TRADES):
            task_id = f"P{floor:02d}-{resource}"
            tasks.append({"id": task_id, "duracao_dias": 2,
                          "local_id": f"P{floor:02d}", "ocupacao_frente": 1,
                          "recursos": {resource: 1}})
            if index > 0:
                links.append({"predecessora_id": f"P{floor:02d}-{TRADES[index-1]}",
                              "sucessora_id": task_id, "tipo": "TI"})
            if floor > 1:
                links.append({"predecessora_id": f"P{floor-1:02d}-{resource}",
                              "sucessora_id": task_id, "tipo": "TI"})
    assert len(tasks) == 200 and len(links) == 346
    return tasks, links


async def main():
    tasks, links = activities_and_links()
    caps = {rid: 2 for rid in TRADES}
    fronts = {f"P{i:02d}": 1 for i in range(1, 51)}
    async with Client(LOB, timeout=90) as client:
        response = parse(await client.call_tool("comparar_cenarios_equipes_frentes", {
            "atividades": tasks,
            "cenarios": [{"nome": "limite-200",
                          "capacidades_recursos": caps,
                          "capacidades_frentes": fronts}],
            "calendarios_recursos": CALENDARS,
            "custos_por_recurso_dia": RATES,
            "data_inicio": DATES,
            "custo_indireto_por_dia_corrido": 75,
            "dependencias": links,
            "custos_mobilizacao_por_recurso": MOB,
            "custos_ociosidade_por_recurso_dia": IDLE,
        }))
    assert response["persistido"] is False
    scenario = response["cenarios"][0]
    used = verify_schedule(scenario, tasks, links, caps, fronts)
    cost = independent_costs(scenario, used, caps)
    print(json.dumps({"valid": True, "activities": len(tasks),
                      "dependencies": len(links), "floors": len(fronts),
                      "days_elapsed": cost["elapsed"],
                      "cost": cost["total"], "idle_unit_days": cost["idle"],
                      "capacity_limit_tested": 200, "persistido": False}))


if __name__ == "__main__":
    asyncio.run(main())
