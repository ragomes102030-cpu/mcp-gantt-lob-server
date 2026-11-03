"""Calendar-aware facade for the stateless renewable-resource leveler.

All scheduling remains in logical working-day offsets. Calendar dates are a
presentation of integer boundaries; no project data is read or modified.
"""
from __future__ import annotations

from datetime import date, timedelta

from .resource_leveling import nivelar_recursos


def nivelar_recursos_com_calendario(
    atividades: list[dict], capacidades: dict[str, int],
    dependencias: list[dict] | None = None,
    data_inicio: str | None = None, calendario: dict | None = None,
) -> dict:
    """Level resource demands and optionally map whole-day offsets to working dates.

    calendario: {modo: "corridos"|"uteis", dias_semana: [0..6],
                 feriados: ["YYYY-MM-DD"], calendar_id: optional string}.
    modo=uteis requires data_inicio and integer durations, lags, starts.
    """
    if calendario is not None and not isinstance(calendario, dict):
        raise ValueError("calendario deve ser objeto")
    cal = calendario or {}
    modo = cal.get("modo", "corridos")
    if modo not in ("corridos", "uteis"):
        raise ValueError("modo de calendario desconhecido")
    try:
        inicio = date.fromisoformat(data_inicio) if data_inicio is not None else None
    except (ValueError, TypeError):
        raise ValueError("data_inicio deve ser ISO YYYY-MM-DD") from None
    if modo == "uteis" and inicio is None:
        raise ValueError("calendario uteis exige data_inicio")
    dias = cal.get("dias_semana", [0, 1, 2, 3, 4])
    feriados = cal.get("feriados", [])
    if modo == "uteis":
        if (not isinstance(dias, list) or not dias or
                any(type(x) is not int or x not in range(7) for x in dias) or
                len(set(dias)) != len(dias)):
            raise ValueError("dias_semana invalidos")
        if not isinstance(feriados, list) or len(feriados) > 500:
            raise ValueError("feriados invalidos")
        try:
            holidays = {date.fromisoformat(x) for x in feriados}
        except (ValueError, TypeError):
            raise ValueError("feriados devem ser datas ISO") from None
        # Resource leveling currently supports a common calendar, not per-resource shifts.
        for task in atividades:
            if not isinstance(task, dict):
                raise ValueError("atividade invalida")
            for key in ("duracao_dias", "inicio_planejado_dia"):
                if key in task and (type(task[key]) not in (int, float) or
                                    not float(task[key]).is_integer()):
                    raise ValueError("calendario uteis exige duracoes/inicios inteiros")
        for dep in dependencias or []:
            if not isinstance(dep, dict):
                raise ValueError("dependencia invalida")
            lag = dep.get("lag_dias", 0)
            if type(lag) not in (int, float) or not float(lag).is_integer():
                raise ValueError("calendario uteis exige lags inteiros")
    else:
        holidays = set()

    result = nivelar_recursos(atividades, capacidades, dependencias)
    if inicio is None:
        return {**result, "calendario_modo": modo, "calendar_id": cal.get("calendar_id")}
    if modo == "uteis":
        max_offset = result["duracao_total_dias"]
        if max_offset > 36500:
            raise ValueError("limite de 36500 dias uteis excedido")
        # Bound the scan: dates cannot exceed Python's date range.
        workdays = []
        cursor = inicio
        needed = int(max_offset) + 1
        while len(workdays) < needed:
            if cursor.weekday() in dias and cursor not in holidays:
                workdays.append(cursor)
            try:
                cursor += timedelta(days=1)
            except OverflowError:
                raise ValueError("datas extrapolam calendario valido") from None

        def convert(offset):
            if not float(offset).is_integer():
                raise ValueError("offset fracionario no calendario util")
            return workdays[int(offset)]
    else:
        def convert(offset):
            try:
                return inicio + timedelta(days=offset)
            except OverflowError:
                raise ValueError("datas extrapolam calendario valido") from None

    rows = [{**row,
             "data_inicio": convert(row["inicio_dia"]).isoformat(),
             "data_fim_exclusiva": convert(row["fim_dia"]).isoformat()}
            for row in result["tarefas"]]
    return {**result, "tarefas": rows, "calendario_modo": modo,
            "calendar_id": cal.get("calendar_id"),
            "convencao": "intervalos [inicio,fim); datas finais exclusivas",
            "premissa": result["premissa"] +
                        "; calendario unico para todos recursos; sem turnos/feriados automaticos"}
