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
    custos_mobilizacao_por_recurso: dict[str, float] | None = None,
    custos_ociosidade_por_recurso_dia: dict[str, float] | None = None,
) -> dict:
    """Direct cost = sum(activity duration * resource demand * resource daily rate).

    Indirect cost = schedule duration * overhead daily rate. Optional mobilization
    applies once per reserved unit. Optional idle cost charges available
    capacity-days not consumed, reserved over the whole project timeline.
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
    def optional_rates(values, label):
        if values is None:
            return {}
        if not isinstance(values, dict):
            raise ValueError(f"{label} deve ser dicionario")
        out = {}
        for rid, amount in values.items():
            if rid not in rates:
                raise ValueError(f"{label}: recurso desconhecido {rid}")
            out[rid] = _valor(amount, f"{label} {rid}")
        return out

    mobilization_rates = optional_rates(custos_mobilizacao_por_recurso, "mobilizacao")
    idle_rates = optional_rates(custos_ociosidade_por_recurso_dia, "ociosidade")
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
        busy_days = {rid: 0.0 for rid in capacities}
        for row in schedule["tarefas"]:
            duration = row["fim_dia"] - row["inicio_dia"]
            for rid, units in row["recursos"].items():
                if rid not in rates:
                    raise ValueError(f"Falta custo por recurso/dia: {rid}")
                direct += duration * units * rates[rid]
                busy_days[rid] += duration * units
        duration = schedule["duracao_total_dias"]
        overhead = duration * indirect
        mobilization = sum(cap * mobilization_rates.get(rid, 0)
                           for rid, cap in capacities.items())
        idle_units_days = {
            rid: max(0.0, cap * duration - busy_days[rid])
            for rid, cap in capacities.items()
        }
        idle_cost = sum(idle_units_days[rid] * idle_rates.get(rid, 0)
                        for rid in capacities)
        total = direct + overhead + mobilization + idle_cost
        if not math.isfinite(total) or total > 1e15:
            raise ValueError("Custo total excede limite")
        evaluated.append({
            "nome": name, "duracao_total_dias": duration,
            "custo_direto": round(direct, 2),
            "custo_indireto": round(overhead, 2),
            "custo_mobilizacao": round(mobilization, 2),
            "custo_ociosidade": round(idle_cost, 2),
            "ociosidade_unidades_dia": {rid: round(v, 6) for rid, v in idle_units_days.items()},
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
            "mobilizacao opcional por unidade de capacidade reservada",
            "ociosidade opcional: capacidade vezes prazo menos consumo; reserva integral",
            "taxa de ociosidade incremental ao custo direto para evitar dupla contagem",
            "nao inclui horas extras, reajustes, riscos nem janela de mobilizacao",
        ],
    }
