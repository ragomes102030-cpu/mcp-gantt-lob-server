"""Stateless deterministic renewable-resource capacity leveling.

Input tasks are atomic, non-preemptive, with start offsets in days.
This heuristic preserves FS dependencies and never schedules demand above capacity.
It minimizes neither makespan nor cost. No persisted state is read/written.
"""
from __future__ import annotations

import math


def _nonnegative(value, name, allow_zero=True):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{name} deve ser numero finito")
    if value < 0 or (not allow_zero and value == 0) or value > 1e6:
        raise ValueError(f"{name} fora do intervalo permitido")
    return float(value)


def nivelar_recursos(atividades: list[dict], capacidades: dict[str, int],
                    dependencias: list[dict] | None = None) -> dict:
    """Heuristic priority: planned start, then original input order.

    Task: id, duracao_dias, inicio_planejado_dia (optional), recursos {resource_id: integer}.
    Dependency: predecessora_id, sucessora_id, tipo='TI', lag_dias>=0.
    Independent tasks may run concurrently when capacities permit.
    """
    if not isinstance(atividades, list) or not 1 <= len(atividades) <= 200:
        raise ValueError("Informe 1..200 atividades")
    if not isinstance(capacidades, dict) or not 1 <= len(capacidades) <= 100:
        raise ValueError("Informe 1..100 capacidades")
    caps = {}
    for rid, cap in capacidades.items():
        if not isinstance(rid, str) or not rid.strip() or len(rid) > 100:
            raise ValueError("ID de recurso invalido")
        if type(cap) is not int or not 1 <= cap <= 10000:
            raise ValueError("Capacidade deve ser inteiro positivo")
        caps[rid] = cap
    tasks = {}
    for index, obj in enumerate(atividades):
        if not isinstance(obj, dict):
            raise ValueError("Atividade invalida")
        tid = obj.get("id")
        if not isinstance(tid, str) or not tid.strip() or len(tid) > 100 or tid in tasks:
            raise ValueError("ID ausente, longo ou duplicado")
        duration = _nonnegative(obj.get("duracao_dias"), "duracao_dias", False)
        planned = _nonnegative(obj.get("inicio_planejado_dia", 0), "inicio_planejado_dia")
        demand = obj.get("recursos", {})
        if not isinstance(demand, dict) or not demand:
            raise ValueError("Atividade exige ao menos um recurso")
        d = {}
        for rid, units in demand.items():
            if rid not in caps or type(units) is not int or units < 1 or units > caps[rid]:
                raise ValueError(f"{tid}: demanda indisponivel ou acima da capacidade: {rid}")
            d[rid] = units
        tasks[tid] = {"id": tid, "duracao_dias": duration, "inicio_planejado_dia": planned,
                      "recursos": d, "_index": index}
    links = dependencias if dependencias is not None else []
    if not isinstance(links, list) or len(links) > 1000:
        raise ValueError("Dependencias invalidas")
    incoming = {tid: [] for tid in tasks}
    outbound = {tid: [] for tid in tasks}
    for dep in links:
        if not isinstance(dep, dict):
            raise ValueError("Dependencia invalida")
        p, s = dep.get("predecessora_id"), dep.get("sucessora_id")
        if p not in tasks or s not in tasks or p == s or dep.get("tipo", "TI") != "TI":
            raise ValueError("Dependencia TI com IDs validos requerida")
        lag = _nonnegative(dep.get("lag_dias", 0), "lag_dias")
        if any(pred == p for pred, _ in incoming[s]):
            raise ValueError("Dependencia duplicada")
        incoming[s].append((p, lag))
        outbound[p].append(s)
    degree = {tid: len(incoming[tid]) for tid in tasks}
    ready = [tid for tid in tasks if degree[tid] == 0]
    scheduled = {}
    while ready:
        tid = min(ready, key=lambda x: (tasks[x]["inicio_planejado_dia"], tasks[x]["_index"]))
        ready.remove(tid)
        task = tasks[tid]
        start = max([task["inicio_planejado_dia"]] +
                    [scheduled[p]["fim_dia"] + lag for p, lag in incoming[tid]])
        end = start + task["duracao_dias"]
        # Shift to the earliest release time for a conflicting capacity interval.
        # Half-open [start,end) intervals allow handovers without artificial delay.
        while True:
            release = []
            for resource, units in task["recursos"].items():
                events = [(start, units), (end, -units)]
                for other in scheduled.values():
                    if resource not in other["recursos"]:
                        continue
                    a, b = other["inicio_dia"], other["fim_dia"]
                    if a < end and b > start:
                        events.extend([(max(a, start), other["recursos"][resource]),
                                       (min(b, end), -other["recursos"][resource])])
                events.sort(key=lambda pair: (pair[0], pair[1]))
                level = 0
                for _, delta in events:
                    level += delta
                    if level > caps[resource]:
                        release.extend(other["fim_dia"] for other in scheduled.values()
                                       if resource in other["recursos"] and
                                       other["inicio_dia"] < end and other["fim_dia"] > start)
                        break
            if not release:
                break
            next_start = min(x for x in release if x > start + 1e-9)
            start = next_start
            end = start + task["duracao_dias"]
        scheduled[tid] = {"id": tid, "inicio_dia": round(start, 6),
                          "fim_dia": round(end, 6),
                          "atraso_recursos_dias": round(start - max(
                              [task["inicio_planejado_dia"]] +
                              [scheduled[p]["fim_dia"] + lag for p, lag in incoming[tid]]), 6),
                          "recursos": task["recursos"]}
        for child in outbound[tid]:
            degree[child] -= 1
            if degree[child] == 0:
                ready.append(child)
    if len(scheduled) != len(tasks):
        raise ValueError("Rede com ciclo")
    result = list(scheduled.values())
    return {"schema_version": "1.0", "metodo": "heuristica_serial_prioridade_inicio",
            "tarefas": result, "duracao_total_dias": max(x["fim_dia"] for x in result),
            "total_tarefas": len(result), "persistido": False,
            "premissa": "tarefas nao preemptivas; recursos renovaveis; dias relativos; sem calendario nem otimizacao global"}
