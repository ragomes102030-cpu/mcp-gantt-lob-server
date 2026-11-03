"""Stateless finite-capacity scheduling with a distinct calendar for each resource.

Daily-granularity discrete serial schedule generation. Activities work only on
days when ALL assigned resources are available. Non-working gaps are permitted;
activity resource demands remain fixed on each productive day. This is not an
optimal RCPSP solver and does not infer labor laws, holidays or shifts.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from math import isfinite


_HORIZON = 3650


def _id(value, label):
    if not isinstance(value, str) or not 0 < len(value.strip()) <= 100:
        raise ValueError(f"{label} ausente ou invalido")
    return value.strip()


def _integer(value, label, *, minimum=0, maximum=100000):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label} deve ser inteiro no intervalo {minimum}..{maximum}")
    return value


def _parse_calendar(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label}: informe objeto")
    weekdays = value.get("dias_semana", [0, 1, 2, 3, 4])
    if (not isinstance(weekdays, list) or not weekdays or
            any(type(d) is not int or d < 0 or d > 6 for d in weekdays) or
            len(weekdays) != len(set(weekdays))):
        raise ValueError(f"{label}: dias_semana invalidos")
    holidays = value.get("feriados", [])
    if not isinstance(holidays, list) or len(holidays) > 500:
        raise ValueError(f"{label}: feriados invalidos")
    try:
        exclusions = {date.fromisoformat(v) for v in holidays}
    except (ValueError, TypeError):
        raise ValueError(f"{label}: feriados exigem ISO YYYY-MM-DD") from None
    return set(weekdays), exclusions


def nivelar_calendarios_por_equipe(
    atividades: list[dict],
    capacidades_recursos: dict[str, int],
    calendarios_recursos: dict[str, dict],
    data_inicio: str,
    dependencias: list[dict] | None = None,
    capacidades_frentes: dict[str, int] | None = None,
) -> dict:
    """Schedule activities with per-resource workdays and optional physical slots.

    Activity: id, duracao_dias integer > 0, recursos {name: units},
    optional local_id and ocupacao_frente (required if front caps are supplied).
    Dependency: predecessora_id, sucessora_id, tipo='TI', lag_dias integer >=0,
    with lag measured in CIVIL days from the predecessor's exclusive boundary.

    Output days are calendar dates. data_fim_exclusiva is the first COMMON
    available workday AFTER the final productive day, not the next civil day.
    The boundary may include excluded dates (weekends/holidays).
    """
    if not isinstance(atividades, list) or not 1 <= len(atividades) <= 200:
        raise ValueError("Informe 1..200 atividades")
    if not isinstance(capacidades_recursos, dict) or not 1 <= len(capacidades_recursos) <= 100:
        raise ValueError("Informe 1..100 recursos")
    if not isinstance(calendarios_recursos, dict):
        raise ValueError("calendarios_recursos deve ser objeto")
    if set(capacidades_recursos) != set(calendarios_recursos):
        raise ValueError("Cada recurso requer um calendario explicito")
    try:
        origin = date.fromisoformat(data_inicio)
    except (TypeError, ValueError):
        raise ValueError("data_inicio exige ISO YYYY-MM-DD") from None
    if not 1900 <= origin.year <= 9900:
        raise ValueError("Data de inicio fora do dominio")
    caps = {}
    calendars = {}
    for resource, capacity in capacidades_recursos.items():
        resource = _id(resource, "recurso")
        caps[resource] = _integer(capacity, "capacidade do recurso", minimum=1, maximum=10000)
        calendars[resource] = _parse_calendar(calendarios_recursos[resource], resource)
    fronts = capacidades_frentes if capacidades_frentes is not None else {}
    if not isinstance(fronts, dict) or len(fronts) > 100:
        raise ValueError("capacidades_frentes invalidas")
    front_caps = {
        _id(loc, "local_id"): _integer(cap, "capacidade de frente", minimum=1, maximum=10000)
        for loc, cap in fronts.items()
    }
    tasks = {}
    for index, row in enumerate(atividades):
        if not isinstance(row, dict):
            raise ValueError("atividade deve ser objeto")
        tid = _id(row.get("id"), "id")
        if tid in tasks:
            raise ValueError("id de atividade duplicado")
        duration = _integer(row.get("duracao_dias"), "duracao_dias", minimum=1, maximum=3650)
        demand = row.get("recursos")
        if not isinstance(demand, dict) or not demand:
            raise ValueError("recursos da atividade obrigatorios")
        d = {}
        for resource, units in demand.items():
            if resource not in caps:
                raise ValueError("recurso nao declarado")
            d[resource] = _integer(units, "demanda", minimum=1, maximum=caps[resource])
        loc, occ = None, 0
        if front_caps:
            loc = _id(row.get("local_id"), "local_id")
            if loc not in front_caps:
                raise ValueError("frente nao declarada")
            occ = _integer(row.get("ocupacao_frente", 1),
                           "ocupacao_frente", minimum=1, maximum=front_caps[loc])
        starts_offset = _integer(row.get("inicio_minimo_dias_corridos", 0),
                                 "inicio_minimo_dias_corridos", minimum=0, maximum=_HORIZON)
        tasks[tid] = {
            "id": tid, "duracao_dias": duration, "recursos": d, "local_id": loc,
            "ocupacao_frente": occ, "inicio_minimo_dias_corridos": starts_offset,
            "_index": index,
        }
    dependencies = [] if dependencias is None else dependencias
    if not isinstance(dependencies, list) or len(dependencies) > 1000:
        raise ValueError("dependencias invalidas")
    incoming = {tid: [] for tid in tasks}
    following = {tid: [] for tid in tasks}
    for link in dependencies:
        if not isinstance(link, dict):
            raise ValueError("dependencia invalida")
        p, s = link.get("predecessora_id"), link.get("sucessora_id")
        if p not in tasks or s not in tasks or p == s or link.get("tipo", "TI") != "TI":
            raise ValueError("Vinculo TI com IDs validos exigido")
        lag = _integer(link.get("lag_dias", 0), "lag_dias", minimum=0, maximum=_HORIZON)
        if any(x[0] == p for x in incoming[s]):
            raise ValueError("dependencia duplicada")
        incoming[s].append((p, lag))
        following[p].append(s)

    degree = {tid: len(incoming[tid]) for tid in tasks}
    ready = [tid for tid in tasks if degree[tid] == 0]
    scheduled = {}
    resource_usage = defaultdict(lambda: defaultdict(int))
    front_usage = defaultdict(lambda: defaultdict(int))
    while ready:
        tid = min(ready, key=lambda k: (tasks[k]["inicio_minimo_dias_corridos"],
                                        tasks[k]["_index"]))
        ready.remove(tid)
        task = tasks[tid]
        min_date = origin + timedelta(days=task["inicio_minimo_dias_corridos"])
        for predecessor, lag in incoming[tid]:
            min_date = max(min_date, scheduled[predecessor]["_finish"] + timedelta(days=lag))
        resource_ids = list(task["recursos"])
        if not set.intersection(*(calendars[r][0] for r in resource_ids)):
            raise ValueError(f"Sem capacidade ou dias comuns para atividade {tid}")
        def active(day):
            return all(day.weekday() in calendars[r][0] and
                       day not in calendars[r][1] for r in resource_ids)

        allocation = None
        for shift in range(_HORIZON):
            candidate = min_date + timedelta(days=shift)
            if not active(candidate):
                continue
            productive = []
            cursor = candidate
            # Do not silently accept an impossible intersection of calendars.
            for _ in range(_HORIZON):
                if active(cursor):
                    productive.append(cursor)
                    if len(productive) == task["duracao_dias"]:
                        break
                cursor += timedelta(days=1)
            if len(productive) != task["duracao_dias"]:
                continue
            if any(
                any(resource_usage[r][day] + units > caps[r]
                    for r, units in task["recursos"].items()) or
                (task["local_id"] is not None and
                 front_usage[task["local_id"]][day] + task["ocupacao_frente"] >
                 front_caps[task["local_id"]])
                for day in productive
            ):
                continue
            boundary = productive[-1] + timedelta(days=1)
            for _ in range(_HORIZON):
                if active(boundary):
                    break
                boundary += timedelta(days=1)
            else:
                raise ValueError("Calendarios nao possuem proximo dia util comum")
            allocation = (productive, boundary)
            break
        if allocation is None:
            raise ValueError(f"Sem capacidade ou dias comuns para atividade {tid}")
        days, boundary = allocation
        for day in days:
            for resource, units in task["recursos"].items():
                resource_usage[resource][day] += units
            if task["local_id"] is not None:
                front_usage[task["local_id"]][day] += task["ocupacao_frente"]
        scheduled[tid] = {
            "id": tid, "data_inicio": days[0].isoformat(),
            "data_ultimo_dia_trabalhado": days[-1].isoformat(),
            "data_fim_exclusiva": boundary.isoformat(),
            "dias_produtivos": [d.isoformat() for d in days],
            "duracao_dias_trabalho": task["duracao_dias"],
            "recursos": task["recursos"], "local_id": task["local_id"],
            "ocupacao_frente": task["ocupacao_frente"],
            "_finish": boundary,
        }
        for successor in following[tid]:
            degree[successor] -= 1
            if degree[successor] == 0:
                ready.append(successor)
    if len(scheduled) != len(tasks):
        raise ValueError("Rede de dependencias ciclica")
    end = max(x["_finish"] for x in scheduled.values())
    output = [{k: v for k, v in row.items() if k != "_finish"}
              for row in scheduled.values()]
    return {
        "schema_version": "1.0", "calculation_version": "resource-team-calendar-v1",
        "metodo": "programacao_serial_por_calendario_e_capacidade",
        "data_inicio_projeto": origin.isoformat(),
        "data_fim_projeto_exclusiva": end.isoformat(),
        "duracao_total_dias_corridos": (end - origin).days,
        "total_tarefas": len(output), "tarefas": output,
        "persistido": False,
        "premissas": [
            "duracao em dias produtivos inteiros; lacunas nao uteis permitidas",
            "cada tarefa exige disponibilidade simultanea de todos recursos alocados",
            "lag TI medido em dias civis a partir do limite exclusivo",
            "capacidades constantes; equipes nao preemptivas em dias produtivos",
            "fim exclusivo e proximo dia util comum apos ultimo dia produtivo",
            "heuristica deterministica; nao garante prazo/custo global otimo",
        ],
    }
