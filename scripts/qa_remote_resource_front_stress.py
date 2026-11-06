"""Remote QA stress: 8 floors, 32 tasks, shared teams, fronts and holidays.

Independent checks on every productive day validate capacity, dependency
order, calendar legality, and scenario cost accounting. Synthetic only.
"""
import asyncio
import json
from collections import defaultdict
from datetime import date, timedelta

from fastmcp import Client
from qa_remote_calendar_parity import LOB, parse

TRADES = ("estrutura", "alvenaria", "eletrica", "acabamento")
DATES = "2026-11-09"
CALENDARS = {
    "estrutura": {"dias_semana": [0, 1, 2, 3, 4], "feriados": ["2026-11-20"]},
    "alvenaria": {"dias_semana": [0, 1, 2, 3, 4], "feriados": ["2026-11-16"]},
    "eletrica": {"dias_semana": [0, 1, 2, 3, 4, 5], "feriados": []},
    "acabamento": {"dias_semana": [0, 1, 2, 3, 4], "feriados": ["2026-11-27"]},
}
RATES = {"estrutura": 150, "alvenaria": 120, "eletrica": 180, "acabamento": 130}
IDLE = {k: 8 for k in TRADES}
MOB = {k: 100 for k in TRADES}


def model():
    tasks = []
    dependencies = []
    for floor in range(1, 9):
        for index, resource in enumerate(TRADES):
            tid = f"P{floor:02d}-{resource}"
            tasks.append({
                "id": tid, "duracao_dias": 2, "local_id": f"P{floor:02d}",
                "ocupacao_frente": 1, "recursos": {resource: 1},
            })
            if index:
                dependencies.append({
                    "predecessora_id": f"P{floor:02d}-{TRADES[index-1]}",
                    "sucessora_id": tid, "tipo": "TI",
                })
            if floor > 1:
                dependencies.append({
                    "predecessora_id": f"P{floor-1:02d}-{resource}",
                    "sucessora_id": tid, "tipo": "TI",
                })
    assert len(tasks) == 32 and len(dependencies) == 52
    return tasks, dependencies


def verify_schedule(output, tasks, dependencies, caps, fronts):
    rows = {r["id"]: r for r in output["tarefas"]}
    assert set(rows) == {t["id"] for t in tasks}
    resource_usage = defaultdict(int)
    front_usage = defaultdict(int)
    used = {name: 0 for name in TRADES}
    for task in tasks:
        row = rows[task["id"]]
        productive = row["dias_produtivos"]
        assert len(productive) == task["duracao_dias"]
        assert productive == sorted(set(productive))
        assert row["recursos"] == task["recursos"]
        assert row["local_id"] == task["local_id"]
        for iso in productive:
            day = date.fromisoformat(iso)
            for res, demand in task["recursos"].items():
                assert day.weekday() in CALENDARS[res]["dias_semana"], (row, iso)
                assert iso not in CALENDARS[res]["feriados"], (row, iso)
                resource_usage[(res, iso)] += demand
                used[res] += demand
            front_usage[(task["local_id"], iso)] += task["ocupacao_frente"]
        assert row["data_inicio"] == productive[0]
        assert date.fromisoformat(row["data_fim_exclusiva"]) > date.fromisoformat(productive[-1])
    assert all(v <= caps[k[0]] for k, v in resource_usage.items())
    assert all(v <= fronts[k[0]] for k, v in front_usage.items())
    for link in dependencies:
        predecessor = rows[link["predecessora_id"]]
        successor = rows[link["sucessora_id"]]
        assert successor["data_inicio"] >= predecessor["data_fim_exclusiva"], link
    # Persistence marker belongs to top-level comparator response, not each scenario.
    return used


def independent_costs(scenario, used, caps):
    start = date.fromisoformat(DATES)
    end = date.fromisoformat(scenario["data_fim_projeto_exclusiva"])
    elapsed = (end - start).days
    assert scenario["duracao_total_dias_corridos"] == elapsed
    assert elapsed > 0
    available = {rid: 0 for rid in TRADES}
    for index in range(elapsed):
        day = start + timedelta(days=index)
        for rid in TRADES:
            if day.weekday() in CALENDARS[rid]["dias_semana"] and day.isoformat() not in CALENDARS[rid]["feriados"]:
                available[rid] += caps[rid]
    idle = {rid: available[rid] - used[rid] for rid in TRADES}
    assert all(v >= 0 for v in idle.values())
    expected_direct = sum(used[rid] * RATES[rid] for rid in TRADES)
    expected_idle = sum(idle[rid] * IDLE[rid] for rid in TRADES)
    expected_mob = sum(caps[rid] * MOB[rid] for rid in TRADES)
    expected_overhead = elapsed * 75
    assert scenario["disponibilidade_unidades_dia_produtivo"] == available
    assert scenario["consumo_unidades_dia_produtivo"] == used
    assert scenario["ociosidade_unidades_dia_produtivo"] == idle
    assert scenario["custo_direto"] == expected_direct
    assert scenario["custo_ociosidade"] == expected_idle
    assert scenario["custo_mobilizacao"] == expected_mob
    assert scenario["custo_indireto"] == expected_overhead
    assert scenario["custo_total"] == expected_direct + expected_idle + expected_mob + expected_overhead
    return {"elapsed": elapsed, "total": scenario["custo_total"], "idle": sum(idle.values())}


async def main():
    tasks, dependencies = model()
    setups = [
        {"nome": "limitado", "capacidades_recursos": {r: 1 for r in TRADES},
         "capacidades_frentes": {f"P{i:02d}": 1 for i in range(1, 9)}},
        {"nome": "expandido", "capacidades_recursos": {r: 2 for r in TRADES},
         "capacidades_frentes": {f"P{i:02d}": 2 for i in range(1, 9)}},
    ]
    async with Client(LOB, timeout=60) as client:
        names = {tool.name for tool in await client.list_tools()}
        assert "comparar_cenarios_equipes_frentes" in names
        result = parse(await client.call_tool("comparar_cenarios_equipes_frentes", {
            "atividades": tasks,
            "cenarios": setups,
            "calendarios_recursos": CALENDARS,
            "custos_por_recurso_dia": RATES,
            "data_inicio": DATES,
            "custo_indireto_por_dia_corrido": 75,
            "dependencias": dependencies,
            "custos_mobilizacao_por_recurso": MOB,
            "custos_ociosidade_por_recurso_dia": IDLE,
        }))
    assert result["persistido"] is False
    assert len(result["cenarios"]) == 2
    report = {}
    for setup, row in zip(setups, result["cenarios"]):
        assert setup["nome"] == row["nome"]
        used = verify_schedule(row, tasks, dependencies,
                               setup["capacidades_recursos"],
                               setup["capacidades_frentes"])
        report[setup["nome"]] = independent_costs(row, used, setup["capacidades_recursos"])
    print(json.dumps({
        "valid": True, "scenario": "8 floors x 4 trades shared-team-fronts",
        "activities": 32, "dependencies": 52,
        "capacity_conflicts": "checked-every-productive-day",
        "individual_holidays": "checked",
        "costs": report, "persistido": False,
    }))


if __name__ == "__main__":
    asyncio.run(main())
