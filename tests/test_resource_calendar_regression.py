"""Regression tests for stateless resource chains and working-day calendars.

These tests use synthetic QA data and never access project databases.
"""
import pytest

from mcp_gantt_lob.models.lob_rede import calcular_lob_com_vinculos


def _activities(shared_team=True):
    return [
        {"activity_id": "A", "nome": "Servico A", "duracao_dias": 2,
         "equipe_id": "E1"},
        {"activity_id": "B", "nome": "Servico B", "duracao_dias": 2,
         "equipe_id": "E1" if shared_team else "E2"},
    ]


def test_shared_team_serializes_across_services_and_locations():
    result = calcular_lob_com_vinculos(_activities(), ["P01", "P02"], [])
    assert result["persistido"] is False
    assert result["total_tarefas"] == 4
    assert result["duracao_total_dias"] == 8
    tasks = result["tarefas"]
    assert [t["inicio_dia"] for t in tasks] == [0, 2, 4, 6]
    assert [t["fim_dia"] for t in tasks] == [2, 4, 6, 8]
    assert any(
        driver["origem"] == "equipe"
        for task in tasks for driver in task["vinculos_determinantes"]
    )


def test_independent_teams_can_work_in_parallel():
    result = calcular_lob_com_vinculos(
        _activities(shared_team=False), ["P01", "P02"], []
    )
    assert result["duracao_total_dias"] == 4
    starts = {(t["activity_id"], t["location_id"]): t["inicio_dia"]
              for t in result["tarefas"]}
    assert starts[("A", "P01")] == 0
    assert starts[("B", "P01")] == 0


def test_workday_calendar_skips_weekend_and_holiday():
    result = calcular_lob_com_vinculos(
        [{"activity_id": "A", "duracao_dias": 2}],
        ["P01"], [],
        data_inicio="2026-11-06",
        calendario={
            "modo": "uteis", "calendar_id": "qa-weekdays",
            "dias_semana": [0, 1, 2, 3, 4],
            "feriados": ["2026-11-09"],
        },
    )
    assert result["calendario_modo"] == "uteis"
    assert result["tarefas"][0]["data_inicio"] == "2026-11-06"
    assert result["tarefas"][0]["data_fim_exclusiva"] == "2026-11-11"


def test_workday_calendar_rejects_fractional_duration():
    with pytest.raises(ValueError, match="duracoes inteiras"):
        calcular_lob_com_vinculos(
            [{"activity_id": "A", "duracao_dias": 1.5}],
            ["P01"], [],
            data_inicio="2026-11-06",
            calendario={"modo": "uteis"},
        )


def test_explicit_dependency_on_same_team_does_not_duplicate_chain():
    result = calcular_lob_com_vinculos(
        _activities(), ["P01"],
        [{"predecessora_id": "A", "predecessora_local": "P01",
          "sucessora_id": "B", "sucessora_local": "P01", "tipo": "TI"}],
    )
    assert result["duracao_total_dias"] == 4
    assert result["tarefas"][1]["inicio_dia"] == 2
