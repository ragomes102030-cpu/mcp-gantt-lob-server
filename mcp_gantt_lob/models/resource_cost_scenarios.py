"""Compare explicit resource-capacity scenarios by time and cost.

All unit rates are supplied by the caller. Does not fetch price indexes,
infer productivity changes, alter baseline, or optimize globally.
"""
from __future__ import annotations

import math

from .resource_calendar import nivelar_recursos_com_calendario


def _valor(x, campo):
    if type(x) not in (int, float) or not math.isfinite(x) or x < 0 or x > 1e12:
        raise ValueError(f"{campo} deve ser numero nao negativo e finito")
    return float(x)


def comparar_cenarios_custo_prazo(
    atividades: list[dict], cenarios: list[dict],
    custos_por_recurso_dia: dict[str, float],
    custo_indireto_por_dia: float = 0,
    dependencias: list[dict] | None = None,
    data_inicio: str | None = None,
    calendario: dict | None = None,
    prazo_limite_dias: float | None = None,
) -> dict:
    """Direct cost = sum(activity duration * resource demand * resource daily rate).

    Indirect cost = schedule duration * overhead daily rate. Capacity alone
    does not incur cost; idle team reservation, mobilization and overtime
    are not modeled. Durations and quantities are externally supplied.
    """
    if not isinstance(cenarios, list) or not 1 <= len(cenarios) <= 20:
        raise ValueError("Informe de 1 a 20 cenarios")
    if not isinstance(custos_por_recurso_dia, dict) or not custos_por_recurso_dia:
        raise ValueError("Informe custos por recurso/dia")
    rates = {}
    for rid, value in custos_por_recurso_dia.items():
        if not isinstance(rid, str) or not rid.strip():
            raise ValueError("ID de recurso invalido")
        rates[rid] = _valor(value, f"custo de {rid}")
    indirect = _valor(custo_indireto_por_dia, "custo_indireto_por_dia")
    deadline = None if prazo_limite_dias is None else _valor(prazo_limite_dias, "prazo_limite_dias")
    evaluated = []
    used_names = set()
    for scenario in cenarios:
        if not isinstance(scenario, dict):
            raise ValueError("Cenario invalido")
        name = scenario.get("nome")
        if not isinstance(name, str) or not 0 < len(name.strip()) <= 100 or name in used_names:
            raise ValueError("Nome de cenario ausente, longo ou duplicado")
        used_names.add(name)
        capacities = scenario.get("capacidades")
        schedule = nivelar_recursos_com_calendario(
            atividades, capacities, dependencias, data_inicio, calendario
        )
        direct = 0.0
        for row in schedule["tarefas"]:
            duration = row["fim_dia"] - row["inicio_dia"]
            for rid, units in row["recursos"].items():
                if rid not in rates:
                    raise ValueError(f"Falta custo por recurso/dia: {rid}")
                direct += duration * units * rates[rid]
        duration = schedule["duracao_total_dias"]
        overhead = duration * indirect
        total = direct + overhead
        if not math.isfinite(total) or total > 1e15:
            raise ValueError("Custo total excede limite")
        evaluated.append({
            "nome": name, "duracao_total_dias": duration,
            "custo_direto": round(direct, 2),
            "custo_indireto": round(overhead, 2),
            "custo_total": round(total, 2),
            "dentro_prazo": deadline is None or duration <= deadline,
            "capacidades": capacities,
            "tarefas": schedule["tarefas"],
        })
    feasible = [r for r in evaluated if r["dentro_prazo"]]
    best = min(feasible, key=lambda r: (r["custo_total"], r["duracao_total_dias"])) if feasible else None
    return {
        "schema_version": "1.0", "cenarios": evaluated,
        "melhor_cenario_testado": best["nome"] if best else None,
        "prazo_limite_dias": deadline,
        "metodo": "comparacao_cenarios_fornecidos_sem_busca_global",
        "persistido": False,
        "premissas": [
            "custos fornecidos pelo chamador, sem consulta a precos reais",
            "custo direto somente das horas/dias trabalhados, sem ociosidade",
            "capacidade de recurso nao reduz duracao automaticamente",
            "custo indireto proporcional a duracao em dias logicos",
            "nao inclui mobilizacao, horas extras, reajustes ou riscos",
        ],
    }
