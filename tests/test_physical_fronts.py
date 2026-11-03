"""Physical front conflicts, independent floors, explicit precedence and dates."""
import pytest
from mcp_gantt_lob.models.physical_fronts import nivelar_frentes_de_trabalho


def task(id, local, resource):
    return {"id": id, "duracao_dias": 2, "local_id": local,
            "recursos": {resource: 1}}


def test_same_front_prevents_two_distinct_teams_simultaneously():
    r = nivelar_frentes_de_trabalho(
        [task("A", "P01", "alvenaria"), task("B", "P01", "eletrica")],
        {"alvenaria": 1, "eletrica": 1}, {"P01": 1})
    assert r["duracao_total_dias"] == 4
    assert [t["inicio_dia"] for t in r["tarefas"]] == [0, 2]
    assert r["tarefas"][1]["local_id"] == "P01"
    assert all("__frente_fisica__:" not in str(t["recursos"]) for t in r["tarefas"])
    assert r["persistido"] is False


def test_two_fronts_allow_parallel_activities():
    r = nivelar_frentes_de_trabalho(
        [task("A", "P01", "alvenaria"), task("B", "P02", "eletrica")],
        {"alvenaria": 1, "eletrica": 1}, {"P01": 1, "P02": 1})
    assert r["duracao_total_dias"] == 2
    assert [t["inicio_dia"] for t in r["tarefas"]] == [0, 0]


def test_front_capacity_two_allows_parallel_workers():
    r = nivelar_frentes_de_trabalho(
        [task("A", "P01", "alvenaria"), task("B", "P01", "eletrica")],
        {"alvenaria": 1, "eletrica": 1}, {"P01": 2})
    assert r["duracao_total_dias"] == 2


def test_front_occupation_two_blocks_other_activity():
    a = {**task("A", "P01", "alvenaria"), "ocupacao_frente": 2}
    r = nivelar_frentes_de_trabalho(
        [a, task("B", "P01", "eletrica")],
        {"alvenaria": 1, "eletrica": 1}, {"P01": 2})
    assert r["duracao_total_dias"] == 4


def test_shared_team_across_different_fronts_serialized():
    r = nivelar_frentes_de_trabalho(
        [task("A", "P01", "alvenaria"), task("B", "P02", "alvenaria")],
        {"alvenaria": 1}, {"P01": 1, "P02": 1})
    assert r["duracao_total_dias"] == 4


def test_front_calendar_keeps_exclusive_dates():
    r = nivelar_frentes_de_trabalho(
        [task("A", "P01", "alvenaria"), task("B", "P01", "eletrica")],
        {"alvenaria": 1, "eletrica": 1}, {"P01": 1},
        data_inicio="2026-11-06",
        calendario={"modo": "uteis", "feriados": ["2026-11-09"]})
    assert [t["data_inicio"] for t in r["tarefas"]] == [
        "2026-11-06", "2026-11-11"]
    assert r["tarefas"][-1]["data_fim_exclusiva"] == "2026-11-13"


def test_explicit_dependency_still_honored():
    r = nivelar_frentes_de_trabalho(
        [task("A", "P01", "alvenaria"), task("B", "P02", "eletrica")],
        {"alvenaria": 1, "eletrica": 1}, {"P01": 1, "P02": 1},
        [{"predecessora_id": "A", "sucessora_id": "B", "tipo": "TI", "lag_dias": 1}])
    assert r["tarefas"][1]["inicio_dia"] == 3


@pytest.mark.parametrize("front_caps,local,occupancy", [
    ({"P01": 1}, "P02", 1),
    ({"P01": 1}, "P01", 2),
    ({"P01": 0}, "P01", 1),
])
def test_invalid_front_rejected(front_caps, local, occupancy):
    a = {**task("A", local, "alvenaria"), "ocupacao_frente": occupancy}
    with pytest.raises(ValueError):
        nivelar_frentes_de_trabalho([a], {"alvenaria": 1}, front_caps)
