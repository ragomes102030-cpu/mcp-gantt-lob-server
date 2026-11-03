"""Tests for opt-in renewable resource capacity leveling."""
import pytest
from mcp_gantt_lob.models.resource_leveling import nivelar_recursos


def task(id, duration=2, start=0, resources=None):
    return {"id": id, "duracao_dias": duration, "inicio_planejado_dia": start,
            "recursos": resources or {"pedreiro": 1}}


def test_one_resource_serializes_two_independent_tasks():
    r = nivelar_recursos([task("A"), task("B")], {"pedreiro": 1})
    assert r["duracao_total_dias"] == 4
    assert [(x["inicio_dia"], x["fim_dia"]) for x in r["tarefas"]] == [(0, 2), (2, 4)]
    assert r["tarefas"][1]["atraso_recursos_dias"] == 2
    assert r["persistido"] is False


def test_capacity_two_allows_parallel_tasks():
    r = nivelar_recursos([task("A"), task("B")], {"pedreiro": 2})
    assert r["duracao_total_dias"] == 2
    assert [x["inicio_dia"] for x in r["tarefas"]] == [0, 0]


def test_multiresource_contention_requires_both_available():
    a = task("A", resources={"pedreiro": 1})
    b = task("B", resources={"eletricista": 1})
    c = task("C", resources={"pedreiro": 1, "eletricista": 1})
    r = nivelar_recursos([a, b, c], {"pedreiro": 1, "eletricista": 1})
    times = {x["id"]: (x["inicio_dia"], x["fim_dia"]) for x in r["tarefas"]}
    assert times == {"A": (0, 2), "B": (0, 2), "C": (2, 4)}


def test_fs_dependency_and_lag_preserved_even_with_capacity():
    r = nivelar_recursos([task("A", duration=3), task("B")], {"pedreiro": 2},
                         [{"predecessora_id": "A", "sucessora_id": "B", "lag_dias": 1}])
    assert [x["inicio_dia"] for x in r["tarefas"]] == [0, 4]
    assert r["duracao_total_dias"] == 6


def test_higher_demand_blocks_parallel_assignment():
    a = task("A", resources={"pedreiro": 2})
    b = task("B", resources={"pedreiro": 1})
    r = nivelar_recursos([a, b], {"pedreiro": 2})
    assert r["duracao_total_dias"] == 4


def test_fractional_work_duration():
    r = nivelar_recursos([task("A", duration=1.5), task("B", duration=1.5)],
                         {"pedreiro": 1})
    assert r["duracao_total_dias"] == 3


def test_overcapacity_rejected():
    with pytest.raises(ValueError, match="demanda"):
        nivelar_recursos([task("A", resources={"pedreiro": 3})], {"pedreiro": 2})


def test_cycles_rejected():
    with pytest.raises(ValueError, match="ciclo"):
        nivelar_recursos([task("A"), task("B")], {"pedreiro": 1}, [
            {"predecessora_id": "A", "sucessora_id": "B"},
            {"predecessora_id": "B", "sucessora_id": "A"}])


def test_unknown_resource_rejected():
    with pytest.raises(ValueError, match="demanda"):
        nivelar_recursos([task("A", resources={"guindaste": 1})], {"pedreiro": 1})
