"""Edificio Arquimedes QA-001: 30 activities, shared CPM/LOB network.

Remote public MCP integration uses only fabricated data. Independent DAG oracle
prevents both engines from agreeing on an incorrect answer unnoticed.
"""
import asyncio
import json

from fastmcp import Client
from qa_remote_calendar_parity import CRONOGRAMA, LOB, parse
from qa_remote_three_mcp_chain import EAP


def payload():
    floors = [f"P{i:02d}" for i in range(1, 9)]
    trades = [("EST", 5), ("ALV", 3), ("INS", 4)]
    tasks = [{"id": f"{trade}-{floor}", "duracao_dias": duration}
             for floor in floors for trade, duration in trades]
    tasks.extend({"id": f"APOIO-{i}", "duracao_dias": 2}
                 for i in range(1, 7))
    links = []
    for floor_index, floor in enumerate(floors):
        for trade_index, (trade, _) in enumerate(trades):
            if floor_index:
                links.append({"predecessora_id": f"{trade}-{floors[floor_index-1]}",
                              "sucessora_id": f"{trade}-{floor}",
                              "tipo": "TI", "lag_dias": 0})
            if trade_index:
                links.append({"predecessora_id": f"{trades[trade_index-1][0]}-{floor}",
                              "sucessora_id": f"{trade}-{floor}",
                              "tipo": "TI", "lag_dias": 1})
    links.extend({"predecessora_id": f"APOIO-{i}",
                  "sucessora_id": f"APOIO-{i+1}", "tipo": "TI"}
                 for i in range(1, 6))
    nodes = [{"eap_id": "1", "nome": "Obra QA", "nivel": 1},
             {"eap_id": "1.1", "parent_id": "1", "nome": "Pavimentos", "nivel": 2},
             {"eap_id": "1.2", "parent_id": "1", "nome": "Apoio", "nivel": 2}]
    nodes.extend({
        "eap_id": f"1.{1 if i < 24 else 2}.{i+1 if i < 24 else i-23}",
        "parent_id": "1.1" if i < 24 else "1.2",
        "nome": item["id"], "nivel": 3
    } for i, item in enumerate(tasks))
    return tasks, links, nodes, floors, trades


def independent_dag_duration(tasks, links):
    durations = {item["id"]: item["duracao_dias"] for item in tasks}
    incoming = {k: [] for k in durations}
    for link in links:
        incoming[link["sucessora_id"]].append(
            (link["predecessora_id"], link.get("lag_dias", 0)))
    ends = {}
    for _ in range(len(tasks)):
        progressed = False
        for key, duration in durations.items():
            if key in ends:
                continue
            if all(pred in ends for pred, lag in incoming[key]):
                ends[key] = max([0] + [ends[pred] + lag
                                       for pred, lag in incoming[key]]) + duration
                progressed = True
        if not progressed:
            break
    assert len(ends) == len(tasks), "Network contains a cycle"
    return max(ends.values())


async def main():
    tasks, links, nodes, floors, trades = payload()
    assert (len(tasks), len(links), len(nodes)) == (30, 42, 33)
    oracle_duration = independent_dag_duration(tasks, links)
    assert oracle_duration == 49

    async with Client(EAP, timeout=35) as client:
        eap = parse(await client.call_tool("validar_estrutura_eap",
                                           {"nos": nodes}))
    assert eap["ok"] is True and eap["total_nos"] == 33
    assert not eap["erros"] and eap["persistido"] is False

    async with Client(CRONOGRAMA, timeout=35) as client:
        cpm = parse(await client.call_tool("calcular_cpm_com_evidencia", {
            "atividades": tasks, "dependencias": links,
        }))
    assert cpm["valid"] is True
    assert cpm["persistido"] is False
    assert len(cpm["atividades"]) == 30
    assert cpm["duracao_projeto_dias"] == oracle_duration

    async with Client(LOB, timeout=35) as client:
        lob = parse(await client.call_tool("calcular_linha_balanco", {
            "atividades": [
                {"nome": trade, "tempo_unitario": duration,
                 "numero_equipes": 1, "pulmao_dias": 1}
                for trade, duration in trades
            ],
            "unidades": floors,
            "data_inicio": "2026-11-09",
        }))
    assert lob["persistido"] is False
    assert lob["duracao_total_dias"] == oracle_duration
    assert lob["total_unidades"] == 8
    assert len(lob["atividades"]) == 3
    assert [x["espera_total_dias"] for x in lob["atividades"]] == [0, 14, 7]
    for trade, row in zip(trades, lob["atividades"]):
        assert len(row["unidades"]) == len(floors)
        for unit in row["unidades"]:
            task_id = f"{trade[0]}-{unit['unidade']}"
            cpm_result = next(x for x in cpm["atividades"] if x["id"] == task_id)
            assert unit["inicio_dia"] == cpm_result["ES"], (task_id, unit, cpm_result)
            assert unit["fim_dia"] == cpm_result["EF"], (task_id, unit, cpm_result)

    print(json.dumps({
        "valid": True, "scenario": "Edificio Arquimedes QA-001",
        "eap_nodes": 33, "activities": 30, "dependencies": 42,
        "repetitive_operations": 24, "pavimentos": 8,
        "oracle_days": oracle_duration,
        "cpm_days": cpm["duracao_projeto_dias"],
        "lob_days": lob["duracao_total_dias"],
        "waiting_days": {"ALV": 14, "INS": 7},
        "all_repetitive_activity_dates_equal": True,
        "persistido": False,
    }))


if __name__ == "__main__":
    asyncio.run(main())
