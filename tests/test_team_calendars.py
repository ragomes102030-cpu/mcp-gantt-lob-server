"""Per-resource work calendar and front capacity regression tests."""
import pytest
from mcp_gantt_lob.models.team_calendars import nivelar_calendarios_por_equipe as run

WEEK = {"dias_semana": [0, 1, 2, 3, 4]}
TUE_SAT = {"dias_semana": [1, 2, 3, 4, 5]}


def activity(ident, resources, days=2, loc=None):
    item = {"id": ident, "recursos": resources, "duracao_dias": days}
    if loc:
        item["local_id"] = loc
    return item


def test_distinct_workweeks():
    r = run([activity("A", {"a": 1}), activity("B", {"b": 1})],
            {"a": 1, "b": 1}, {"a": WEEK, "b": TUE_SAT}, "2026-11-06")
    assert r["tarefas"][0]["dias_produtivos"] == ["2026-11-06", "2026-11-09"]
    assert r["tarefas"][1]["dias_produtivos"] == ["2026-11-06", "2026-11-07"]
    assert r["data_fim_projeto_exclusiva"] == "2026-11-10"
    assert r["persistido"] is False


def test_holiday_only_affects_one_team():
    r = run([activity("A", {"a": 1}), activity("B", {"b": 1})],
            {"a": 1, "b": 1},
            {"a": {"feriados": ["2026-11-09"]}, "b": WEEK},
            "2026-11-06")
    assert r["tarefas"][0]["dias_produtivos"] == ["2026-11-06", "2026-11-10"]
    assert r["tarefas"][1]["dias_produtivos"] == ["2026-11-06", "2026-11-09"]


def test_joint_activity_uses_intersection_of_calendars():
    r = run([activity("A", {"a": 1, "b": 1}, days=1)],
            {"a": 1, "b": 1}, {"a": WEEK, "b": TUE_SAT}, "2026-11-06")
    assert r["tarefas"][0]["dias_produtivos"] == ["2026-11-06"]


def test_shared_team_serializes_working_days():
    r = run([activity("A", {"a": 1}), activity("B", {"a": 1})],
            {"a": 1}, {"a": WEEK}, "2026-11-06")
    assert r["tarefas"][1]["data_inicio"] == "2026-11-10"


def test_front_capacity_blocks_independent_teams():
    r = run([activity("A", {"a": 1}, loc="P01"),
             activity("B", {"b": 1}, loc="P01")],
            {"a": 1, "b": 1}, {"a": WEEK, "b": WEEK}, "2026-11-06",
            capacidades_frentes={"P01": 1})
    assert r["tarefas"][1]["data_inicio"] == "2026-11-10"


def test_dependency_uses_exclusive_finish_boundary():
    r = run([activity("A", {"a": 1}), activity("B", {"b": 1}, days=1)],
            {"a": 1, "b": 1}, {"a": WEEK, "b": WEEK}, "2026-11-06",
            dependencias=[{"predecessora_id": "A", "sucessora_id": "B"}])
    assert r["tarefas"][0]["data_fim_exclusiva"] == "2026-11-10"
    assert r["tarefas"][1]["data_inicio"] == "2026-11-10"


def test_no_common_workday_fails():
    with pytest.raises(ValueError, match="Sem capacidade"):
        run([activity("A", {"a": 1, "b": 1}, days=1)],
            {"a": 1, "b": 1},
            {"a": {"dias_semana": [0]}, "b": {"dias_semana": [1]}},
            "2026-11-06")


def test_missing_calendar_fails():
    with pytest.raises(ValueError, match="calendario"):
        run([activity("A", {"a": 1})], {"a": 1}, {}, "2026-11-06")


def test_dependency_cycle_fails():
    with pytest.raises(ValueError, match="ciclica"):
        run([activity("A", {"a": 1}), activity("B", {"a": 1})],
            {"a": 1}, {"a": WEEK}, "2026-11-06",
            dependencias=[
                {"predecessora_id": "A", "sucessora_id": "B"},
                {"predecessora_id": "B", "sucessora_id": "A"},
            ])


def test_invalid_holiday_fails():
    with pytest.raises(ValueError, match="feriados"):
        run([activity("A", {"a": 1})], {"a": 1},
            {"a": {"feriados": ["09/11/2026"]}}, "2026-11-06")
