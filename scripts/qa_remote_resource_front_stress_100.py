"""Production QA workload: 25 floors x 4 trades = 100 activities, 171 FS links.

No mutations, no real projects; validates per-day resource/front capacity,
dependencies, calendar legality and full cost reconciliation.
"""
import asyncio
import json
from fastmcp import Client
from qa_remote_calendar_parity import LOB, parse
from qa_remote_resource_front_stress import (TRADES, DATES, CALENDARS, RATES, IDLE, MOB,
                                             verify_schedule, independent_costs)


def larger_model():
    tasks, links = [], []
    for floor in range(1, 26):
        for index, resource in enumerate(TRADES):
            ident = f"P{floor:02d}-{resource}"
            tasks.append({
                "id": ident, "duracao_dias": 2,
                "local_id": f"P{floor:02d}", "ocupacao_frente": 1,
                "recursos": {resource: 1},
            })
            if index:
                links.append({
                    "predecessora_id": f"P{floor:02d}-{TRADES[index - 1]}",
                    "sucessora_id": ident, "tipo": "TI",
                })
            if floor > 1:
                links.append({
                    "predecessora_id": f"P{floor - 1:02d}-{resource}",
                    "sucessora_id": ident, "tipo": "TI",
                })
    assert len(tasks) == 100 and len(links) == 171
    return tasks, links


async def main():
    tasks, links = larger_model()
    setup = {"nome": "25-pavimentos",
             "capacidades_recursos": {r: 2 for r in TRADES},
             "capacidades_frentes": {f"P{i:02d}": 1 for i in range(1, 26)}}
    async with Client(LOB, timeout=90) as client:
        result = parse(await client.call_tool("comparar_cenarios_equipes_frentes", {
            "atividades": tasks,
            "cenarios": [setup],
            "calendarios_recursos": CALENDARS,
            "custos_por_recurso_dia": RATES,
            "data_inicio": DATES,
            "custo_indireto_por_dia_corrido": 75,
            "dependencias": links,
            "custos_mobilizacao_por_recurso": MOB,
            "custos_ociosidade_por_recurso_dia": IDLE,
        }))
    assert result["persistido"] is False
    row = result["cenarios"][0]
    used = verify_schedule(row, tasks, links,
                           setup["capacidades_recursos"],
                           setup["capacidades_frentes"])
    cost = independent_costs(row, used, setup["capacidades_recursos"])
    print(json.dumps({
        "valid": True,
        "activities": 100, "dependencies": 171,
        "floors": 25, "resources": len(TRADES),
        "days_elapsed": cost["elapsed"],
        "total_cost": cost["total"], "idle_unit_days": cost["idle"],
        "all_daily_constraints_valid": True, "persistido": False,
    }))


if __name__ == "__main__":
    asyncio.run(main())
