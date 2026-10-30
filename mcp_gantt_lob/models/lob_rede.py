"""Motor deterministico de LOB por atividade x local, sem banco ou MCP obrigatorio.

Cada tarefa possui identificadores estaveis, vinculos TI/FS explicitos,
restricoes de inicio e cadeia de equipe sequencial por local. O calendario
(opcional) aplica-se APENAS a dias inteiros; evita misturar dias uteis com
duracoes fracionarias de dias corridos.
"""
from __future__ import annotations

from collections import deque
from datetime import date, datetime, time, timedelta
import math


def _numero(x: object, campo: str, *, positivo: bool = False) -> float:
    try:
        n = float(x)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"{campo} deve ser numerico e finito") from exc
    if not math.isfinite(n) or (positivo and n <= 0) or abs(n) > 1e6:
        raise ValueError(f"{campo} invalido, nao finito ou fora do limite")
    return n


def _id(x: object, campo: str) -> str:
    if not isinstance(x, str) or not 0 < len(x.strip()) <= 100:
        raise ValueError(f"{campo} ausente ou excessivamente longo")
    return x.strip()


def _calendario(calendario: dict | None, inicio: date | None):
    if calendario is None:
        return "corridos", None, set()
    if not isinstance(calendario, dict):
        raise ValueError("calendario deve ser objeto")
    modo = calendario.get("modo", "corridos")
    if modo == "corridos":
        return modo, None, set()
    if modo != "uteis" or inicio is None:
        raise ValueError("calendario uteis exige data_inicio e modo uteis")
    dias = calendario.get("dias_semana", [0, 1, 2, 3, 4])
    if not isinstance(dias, list) or not dias or any(type(x) is not int or x not in range(7) for x in dias) or len(dias) != len(set(dias)):
        raise ValueError("dias_semana devem ser inteiros distintos entre 0 e 6")
    feriados = calendario.get("feriados", [])
    if not isinstance(feriados, list) or len(feriados) > 500:
        raise ValueError("feriados invalidos")
    try:
        dias_feriados = {date.fromisoformat(s) for s in feriados}
    except (ValueError, TypeError) as exc:
        raise ValueError("feriado deve ser data ISO") from exc
    return modo, set(dias), dias_feriados


def calcular_lob_com_vinculos(
    atividades: list[dict], locais: list[str], dependencias: list[dict],
    data_inicio: str | None = None, calendario: dict | None = None,
    restricoes_inicio: list[dict] | None = None,
) -> dict:
    """Rede de tarefas (activity_id, location_id). Vinculos explicitamente TI.

    Cada atividade gera uma tarefa em todos os locais ou em `locais_atividade`.
    Uma mesma equipe_id processa tarefas em ordem de atividades e locais,
    impedindo ocupacao simultanea. Para varias equipes em uma atividade,
    duracao = duracao_dias/numero_equipes (idealizacao declarada).
    """
    if not isinstance(atividades, list) or not 1 <= len(atividades) <= 50:
        raise ValueError("Informe de 1 a 50 atividades")
    if not isinstance(locais, list) or not 1 <= len(locais) <= 100:
        raise ValueError("Informe de 1 a 100 locais")
    local_ids = [_id(x, "location_id") for x in locais]
    if len(set(x.casefold() for x in local_ids)) != len(local_ids):
        raise ValueError("location_id duplicado")
    if not isinstance(dependencias, list) or len(dependencias) > 5000:
        raise ValueError("dependencias invalidas ou excessivas")
    try:
        start = date.fromisoformat(data_inicio) if data_inicio else None
    except (ValueError, TypeError) as exc:
        raise ValueError("data_inicio precisa ser ISO YYYY-MM-DD") from exc
    modo, dias_semana, feriados = _calendario(calendario, start)
    tasks: dict[tuple[str, str], dict] = {}
    team_chains: dict[str, list[tuple[str, str]]] = {}
    ids: set[str] = set()
    for atividade in atividades:
        if not isinstance(atividade, dict):
            raise ValueError("atividade deve ser objeto")
        aid = _id(atividade.get("activity_id"), "activity_id")
        if aid in ids:
            raise ValueError("activity_id duplicado")
        ids.add(aid)
        nome = _id(atividade.get("nome", aid), "nome")
        duration = _numero(atividade.get("duracao_dias"), "duracao_dias", positivo=True)
        teams = atividade.get("numero_equipes", 1)
        if type(teams) is not int or not 1 <= teams <= 100:
            raise ValueError("numero_equipes precisa ser inteiro 1..100")
        d = duration / teams
        team = _id(atividade.get("equipe_id", aid), "equipe_id")
        scope = atividade.get("locais_atividade", local_ids)
        if not isinstance(scope, list) or not scope:
            raise ValueError("locais_atividade precisa ser lista nao vazia")
        if len(set(scope)) != len(scope) or any(x not in local_ids for x in scope):
            raise ValueError("locais_atividade tem locais duplicados/inexistentes")
        # Ordens de execucao sao as declaradas em `locais`, nao as do filtro.
        for local in local_ids:
            if local not in scope:
                continue
            key = (aid, local)
            tasks[key] = {
                "activity_id": aid, "location_id": local, "nome": nome,
                "eap_uid": atividade.get("eap_uid"), "equipe_id": team,
                "numero_equipes": teams, "duracao_dias": d,
            }
            team_chains.setdefault(team, []).append(key)
    if len(tasks) > 2000:
        raise ValueError("Mais de 2000 tarefas atividade-local")
    if modo == "uteis" and any(abs(t["duracao_dias"] - round(t["duracao_dias"])) > 1e-9 for t in tasks.values()):
        raise ValueError("calendario uteis exige duracoes inteiras apos equipes")

    adj: dict[tuple[str, str], list[tuple[tuple[str, str], float, str]]] = {k: [] for k in tasks}
    incoming_count: dict[tuple[str, str], int] = {k: 0 for k in tasks}
    links: set[tuple[tuple[str, str], tuple[str, str]]] = set()
    def edge(pred: tuple[str, str], succ: tuple[str, str], lag: float, origem: str):
        if pred not in tasks or succ not in tasks:
            raise ValueError(f"referencia atividade-local inexistente: {pred} -> {succ}")
        if pred == succ or (pred, succ) in links:
            raise ValueError("autorreferencia ou dependencia duplicada")
        links.add((pred, succ))
        adj[pred].append((succ, lag, origem))
        incoming_count[succ] += 1

    for dep in dependencias:
        if not isinstance(dep, dict) or dep.get("tipo", "TI") != "TI":
            raise ValueError("LOB com vinculos aceita exclusivamente tipo TI; II/TT/IT permanecem no CPM")
        pred = (_id(dep.get("predecessora_id"), "predecessora_id"),
                _id(dep.get("predecessora_local"), "predecessora_local"))
        succ = (_id(dep.get("sucessora_id"), "sucessora_id"),
                _id(dep.get("sucessora_local"), "sucessora_local"))
        lag = _numero(dep.get("lag_dias", 0), "lag_dias")
        if lag < 0:
            raise ValueError("LOB explicita exige lag nao negativo para evitar sobreposicao")
        if modo == "uteis" and lag != round(lag):
            raise ValueError("lag em uteis precisa ser inteiro")
        edge(pred, succ, lag, "dependencia")

    # A mesma equipe usa uma unidade por vez, independentemente do servico.
    for chain in team_chains.values():
        for pred, succ in zip(chain, chain[1:]):
            if (pred, succ) not in links:
                edge(pred, succ, 0.0, "equipe")

    starts_min = {k: 0.0 for k in tasks}
    restrictions = restricoes_inicio or []
    if not isinstance(restrictions, list) or len(restrictions) > 2000:
        raise ValueError("restricoes_inicio invalidas")
    for r in restrictions:
        if not isinstance(r, dict):
            raise ValueError("restricao de inicio invalida")
        key = (_id(r.get("activity_id"), "activity_id"), _id(r.get("location_id"), "location_id"))
        if key not in tasks:
            raise ValueError("restricao para atividade-local inexistente")
        val = _numero(r.get("inicio_minimo_dia"), "inicio_minimo_dia")
        if val < 0 or (modo == "uteis" and val != round(val)):
            raise ValueError("inicio_minimo_dia invalido para calendario")
        starts_min[key] = max(starts_min[key], val)
    starts = dict(starts_min)
    degree = dict(incoming_count)
    queue = deque([key for key in tasks if degree[key] == 0])
    order = []
    drivers = {k: [] for k in tasks}
    while queue:
        key = queue.popleft()
        order.append(key)
        finish = starts[key] + tasks[key]["duracao_dias"]
        for succ, lag, origem in adj[key]:
            candidate = finish + lag
            if candidate > starts[succ] + 1e-9:
                starts[succ] = candidate
                drivers[succ] = [{"activity_id": key[0], "location_id": key[1], "origem": origem}]
            elif abs(candidate - starts[succ]) <= 1e-9:
                drivers[succ].append({"activity_id": key[0], "location_id": key[1], "origem": origem})
            degree[succ] -= 1
            if degree[succ] == 0:
                queue.append(succ)
    if len(order) != len(tasks):
        raise ValueError("Ciclo entre dependencias e cadeias de equipes; LOB recusada")
    prazo = max(starts[k] + t["duracao_dias"] for k, t in tasks.items())

    business_cache: list[date] = []
    if modo == "uteis":
        cursor = start
        # Avoid unbounded computation from abusive input.
        max_offset = round(prazo)
        if max_offset > 36500:
            raise ValueError("Limite de 36500 dias uteis por calculo")
        while len(business_cache) <= max_offset:
            if cursor.weekday() in dias_semana and cursor not in feriados:
                business_cache.append(cursor)
            cursor += timedelta(days=1)

    output = []
    for key in order:
        t = tasks[key]
        inicio = round(starts[key], 6)
        fim = round(starts[key] + t["duracao_dias"], 6)
        row = {**t, "inicio_dia": inicio, "fim_dia": fim,
               "vinculos_determinantes": drivers[key]}
        if start is not None:
            if modo == "uteis":
                d0, d1 = business_cache[round(inicio)], business_cache[round(fim)]
                i_dt, f_dt = datetime.combine(d0, time.min), datetime.combine(d1, time.min)
            else:
                i_dt = datetime.combine(start, time.min) + timedelta(days=inicio)
                f_dt = datetime.combine(start, time.min) + timedelta(days=fim)
            row.update({"data_inicio": i_dt.date().isoformat(),
                        "data_fim_exclusiva": f_dt.date().isoformat(),
                        "data_hora_inicio": i_dt.isoformat(),
                        "data_hora_fim_exclusiva": f_dt.isoformat()})
        output.append(row)
    vinculadas = {k for pred, succ in links for k in (pred, succ)}
    return {"schema_version": "1.0", "calculation_version": "lob-rede-v1",
            "convencao": "intervalo [inicio,fim), datas de dia util em limite exclusivo" if modo=="uteis"
                        else "dias corridos relativos desde marco zero, [inicio,fim)",
            "calendar_id": calendario.get("calendar_id") if isinstance(calendario, dict) else None,
            "calendario_modo": modo,
            "duracao_total_dias": round(prazo, 6), "total_tarefas": len(output),
            "tarefas_sem_vinculo": [{"activity_id": k[0], "location_id": k[1]}
                                   for k in tasks if k not in vinculadas and len(tasks) > 1],
            "tarefas": output, "persistido": False,
            "premissa": "1 equipe logica processa uma tarefa por vez; numero_equipes divide duracao em uma mesma tarefa; lags TI nao negativos"}
