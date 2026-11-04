"""Compare explicitly proposed work-calendar and physical-front scenarios.

No global optimization, no real price lookup, no database and no baseline edits.
Rates and resource/front capacities are supplied by the caller. Idle capacity is
charged ONLY on its own available weekdays/holidays, unlike calendar days.
"""
from __future__ import annotations

from datetime import date, timedelta
import math

from .resource_cost_scenarios import _valor
from .team_calendars import nivelar_calendarios_por_equipe, _parse_calendar


def comparar_cenarios_equipes_frentes(
    atividades: list[dict],
    cenarios: list[dict],
    calendarios_recursos: dict[str, dict],
    custos_por_recurso_dia: dict[str, float],
    data_inicio: str,
    custo_indireto_por_dia_corrido: float = 0,
    dependencias: list[dict] | None = None,
    prazo_limite_dias_corridos: int | None = None,
    custos_mobilizacao_por_recurso: dict[str, float] | None = None,
    custos_ociosidade_por_recurso_dia: dict[str, float] | None = None,
) -> dict:
    """Compare up to 20 supplied scenarios with individual team calendars/fronts.

    Scenario: nome, capacidades_recursos, optional capacidades_frentes.
    Direct: each actual productive day * resource demand * rate.
    Mobilization: each reserved capacity unit once.
    Idle: (resource available capacity-days - occupied unit-days) * idle rate;
    all capacities are assumed reserved from project origin through exclusive
    finish. Indirect overhead: elapsed CIVIL days, not productive days.
    """
    if not isinstance(cenarios, list) or not 1 <= len(cenarios) <= 20:
        raise ValueError("Informe 1..20 cenarios")
    if not isinstance(custos_por_recurso_dia, dict) or not custos_por_recurso_dia:
        raise ValueError("custos_por_recurso_dia deve ser dicionario nao vazio")
    if not isinstance(calendarios_recursos, dict):
        raise ValueError("calendarios_recursos deve ser dicionario")
    try:
        origin = date.fromisoformat(data_inicio)
    except (TypeError, ValueError):
        raise ValueError("data_inicio precisa ser ISO YYYY-MM-DD") from None

    rates = {}
    for rid, cost in custos_por_recurso_dia.items():
        if not isinstance(rid, str) or not rid.strip():
            raise ValueError("recurso com ID invalido")
        rates[rid] = _valor(cost, f"custo de {rid}")
    indirect = _valor(custo_indireto_por_dia_corrido, "custo_indireto_por_dia_corrido")
    if prazo_limite_dias_corridos is not None:
        if type(prazo_limite_dias_corridos) is not int or not 0 <= prazo_limite_dias_corridos <= 36500:
            raise ValueError("prazo_limite_dias_corridos deve ser inteiro nao negativo")

    def validate_optional(values, label):
        if values is None:
            return {}
        if not isinstance(values, dict):
            raise ValueError(f"{label} deve ser dicionario")
        result = {}
        for rid, cost in values.items():
            if rid not in rates:
                raise ValueError(f"{label}: recurso nao declarado {rid}")
            result[rid] = _valor(cost, f"{label} {rid}")
        return result

    mobilization_rates = validate_optional(custos_mobilizacao_por_recurso, "mobilizacao")
    idle_rates = validate_optional(custos_ociosidade_por_recurso_dia, "ociosidade")
    calendars = {rid: _parse_calendar(value, rid)
                 for rid, value in calendarios_recursos.items()}
    if set(rates) != set(calendars):
        raise ValueError("Forneca tarifa e calendario para cada recurso declarado")

    out = []
    names = set()
    for scenario in cenarios:
        if not isinstance(scenario, dict):
            raise ValueError("cenario invalido")
        name = scenario.get("nome")
        if not isinstance(name, str) or not 0 < len(name.strip()) <= 100 or name in names:
            raise ValueError("nome de cenario invalido ou duplicado")
        names.add(name)
        capacities = scenario.get("capacidades_recursos")
        if not isinstance(capacities, dict) or set(capacities) != set(rates):
            raise ValueError("capacidades_recursos devem corresponder as tarifas/calendarios")
        front_caps = scenario.get("capacidades_frentes")
        schedule = nivelar_calendarios_por_equipe(
            atividades, capacities, calendarios_recursos, data_inicio,
            dependencias, front_caps)
        duration = schedule["duracao_total_dias_corridos"]
        finish = date.fromisoformat(schedule["data_fim_projeto_exclusiva"])
        if duration > 36500:
            raise ValueError("prazo excede limite")
        used = {rid: 0 for rid in capacities}
        direct = 0.
        for task in schedule["tarefas"]:
            for rid, demand in task["recursos"].items():
                if rid not in rates:
                    raise ValueError(f"falta tarifa para {rid}")
                effort = len(task["dias_produtivos"]) * demand
                used[rid] += effort
                direct += effort * rates[rid]

        available = {rid: 0 for rid in capacities}
        cursor = origin
        while cursor < finish:
            for rid, (weekdays, holidays) in calendars.items():
                if cursor.weekday() in weekdays and cursor not in holidays:
                    available[rid] += capacities[rid]
            cursor += timedelta(days=1)
        idle = {rid: max(0, available[rid] - used[rid]) for rid in capacities}
        idle_cost = sum(idle[rid] * idle_rates.get(rid, 0) for rid in capacities)
        mobilization = sum(capacities[rid] * mobilization_rates.get(rid, 0)
                           for rid in capacities)
        overhead = duration * indirect
        total = direct + idle_cost + mobilization + overhead
        if not math.isfinite(total) or total > 1e15:
            raise ValueError("custo total excede limite")
        out.append({
            "nome": name,
            "duracao_total_dias_corridos": duration,
            "data_fim_projeto_exclusiva": schedule["data_fim_projeto_exclusiva"],
            "custo_direto": round(direct, 2),
            "custo_indireto": round(overhead, 2),
            "custo_mobilizacao": round(mobilization, 2),
            "custo_ociosidade": round(idle_cost, 2),
            "disponibilidade_unidades_dia_produtivo": available,
            "consumo_unidades_dia_produtivo": used,
            "ociosidade_unidades_dia_produtivo": idle,
            "custo_total": round(total, 2),
            "dentro_prazo": (prazo_limite_dias_corridos is None or
                            duration <= prazo_limite_dias_corridos),
            "capacidades_recursos": capacities,
            "capacidades_frentes": front_caps,
            "tarefas": schedule["tarefas"],
        })
    feasible = [s for s in out if s["dentro_prazo"]]
    best = min(feasible, key=lambda x: (x["custo_total"],
                                       x["duracao_total_dias_corridos"])) if feasible else None
    return {
        "schema_version": "1.0",
        "metodo": "comparacao_cenarios_calendarios_frentes_sem_otimizacao_global",
        "cenarios": out,
        "melhor_cenario_testado": best["nome"] if best else None,
        "prazo_limite_dias_corridos": prazo_limite_dias_corridos,
        "persistido": False,
        "premissas": [
            "atividades indivisiveis em duracao de dias produtivos inteiros",
            "custos e cenarios explicitamente fornecidos pelo chamador",
            "custos de pessoal por unidade-dia efetivamente trabalhado",
            "ociosidade considera apenas dias disponiveis do calendario de cada recurso",
            "toda capacidade de cada recurso esta reservada do inicio ate o fim da obra",
            "indireto calculado por dia civil, inclusive finais de semana e feriados",
            "capacidade de frente nao altera produtividade individual",
            "datas finais exclusivas e prazos em dias corridos; vinculos TI civis",
            "sem modelagem horaria, mobilizacoes parciais nem otimizacao global",
        ],
    }
