"""QA: capacity leveling with calendar and public MCP interface."""
import pytest
from mcp_gantt_lob.models.resource_calendar import nivelar_recursos_com_calendario


def tasks(shared=True):
    return [
        {"id": "A", "duracao_dias": 2, "recursos": {"pedreiro": 1}},
        {"id": "B", "duracao_dias": 2, "recursos": {"pedreiro": 1 if shared else 2}},
    ]


def test_shared_capacity_weekend_and_holiday():
    r = nivelar_recursos_com_calendario(
        tasks(), {"pedreiro": 1}, data_inicio="2026-11-06",
        calendario={"modo": "uteis", "feriados": ["2026-11-09"]},
    )
    assert r["duracao_total_dias"] == 4
    assert [t["data_inicio"] for t in r["tarefas"]] == [
        "2026-11-06", "2026-11-11"
    ]
    assert [t["data_fim_exclusiva"] for t in r["tarefas"]] == [
        "2026-11-11", "2026-11-13"
    ]
    assert r["persistido"] is False


def test_parallel_capacity_calendar():
    r = nivelar_recursos_com_calendario(
        tasks(), {"pedreiro": 2}, data_inicio="2026-11-06",
        calendario={"modo": "uteis"},
    )
    assert r["duracao_total_dias"] == 2
    assert all(t["data_inicio"] == "2026-11-06" for t in r["tarefas"])


def test_calendar_legacy_no_dates():
    r = nivelar_recursos_com_calendario(tasks(), {"pedreiro": 1})
    assert r["duracao_total_dias"] == 4
    assert "data_inicio" not in r["tarefas"][0]


def test_calendar_day_counting():
    r = nivelar_recursos_com_calendario(
        tasks(), {"pedreiro": 1}, data_inicio="2026-11-06",
        calendario={"modo": "corridos"},
    )
    assert r["tarefas"][0]["data_fim_exclusiva"] == "2026-11-08"
    assert r["tarefas"][1]["data_fim_exclusiva"] == "2026-11-10"


def test_weekend_start_skips_forward():
    r = nivelar_recursos_com_calendario(
        [tasks()[0]], {"pedreiro": 1}, data_inicio="2026-11-07",
        calendario={"modo": "uteis"},
    )
    assert r["tarefas"][0]["data_inicio"] == "2026-11-09"


def test_fractional_duration_forbidden_on_workdays():
    with pytest.raises(ValueError, match="inteiros"):
        nivelar_recursos_com_calendario(
            [{"id": "A", "duracao_dias": 1.5, "recursos": {"pedreiro": 1}}],
            {"pedreiro": 1}, data_inicio="2026-11-06",
            calendario={"modo": "uteis"},
        )


def test_invalid_holiday_rejected():
    with pytest.raises(ValueError, match="feriados"):
        nivelar_recursos_com_calendario(
            [tasks()[0]], {"pedreiro": 1}, data_inicio="2026-11-06",
            calendario={"modo": "uteis", "feriados": ["09/11/2026"]},
        )


def test_workday_lag_with_dependency():
    r = nivelar_recursos_com_calendario(
        tasks(), {"pedreiro": 2},
        [{"predecessora_id": "A", "sucessora_id": "B", "lag_dias": 1}],
        data_inicio="2026-11-06", calendario={"modo": "uteis"},
    )
    assert [x["inicio_dia"] for x in r["tarefas"]] == [0, 3]
    assert r["tarefas"][1]["data_inicio"] == "2026-11-11"


def test_invalid_calendar_and_missing_date():
    with pytest.raises(ValueError):
        nivelar_recursos_com_calendario(tasks(), {"pedreiro": 1},
                                       calendario={"modo": "uteis"})
    with pytest.raises(ValueError):
        nivelar_recursos_com_calendario(tasks(), {"pedreiro": 1},
                                       data_inicio="2026-11-06",
                                       calendario={"modo": "quinzenal"})
