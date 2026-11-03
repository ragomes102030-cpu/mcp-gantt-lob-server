"""Deterministic QA of time-cost scenario comparison; entirely synthetic."""
import pytest
from mcp_gantt_lob.models.resource_cost_scenarios import comparar_cenarios_custo_prazo

TASKS = [
    {"id": "A", "duracao_dias": 2, "recursos": {"alvenaria": 1}},
    {"id": "B", "duracao_dias": 2, "recursos": {"alvenaria": 1}},
]
SCENARIOS = [
    {"nome": "Uma equipe", "capacidades": {"alvenaria": 1}},
    {"nome": "Duas equipes", "capacidades": {"alvenaria": 2}},
]


def test_time_cost_with_indirect_cost():
    r = comparar_cenarios_custo_prazo(
        TASKS, SCENARIOS, {"alvenaria": 100}, custo_indireto_por_dia=50,
        prazo_limite_dias=3)
    a, b = r["cenarios"]
    assert (a["duracao_total_dias"], a["custo_direto"], a["custo_indireto"], a["custo_total"]) == (4, 400, 200, 600)
    assert (b["duracao_total_dias"], b["custo_direto"], b["custo_indireto"], b["custo_total"]) == (2, 400, 100, 500)
    assert not a["dentro_prazo"] and b["dentro_prazo"]
    assert r["melhor_cenario_testado"] == "Duas equipes"
    assert r["persistido"] is False


def test_zero_overhead_does_not_invent_idle_cost():
    r = comparar_cenarios_custo_prazo(TASKS, SCENARIOS, {"alvenaria": 100})
    assert [x["custo_total"] for x in r["cenarios"]] == [400, 400]
    assert r["melhor_cenario_testado"] == "Duas equipes"


def test_no_scenario_meets_deadline():
    r = comparar_cenarios_custo_prazo(TASKS, SCENARIOS, {"alvenaria": 100},
                                      prazo_limite_dias=1)
    assert r["melhor_cenario_testado"] is None


def test_cost_multi_resource():
    r = comparar_cenarios_custo_prazo(
        [{"id": "A", "duracao_dias": 3, "recursos": {"p": 2, "e": 1}}],
        [{"nome": "Base", "capacidades": {"p": 2, "e": 1}}],
        {"p": 100, "e": 200})
    assert r["cenarios"][0]["custo_direto"] == 1200


def test_working_calendar_retains_exclusive_date_convention():
    r = comparar_cenarios_custo_prazo(
        [TASKS[0]], [SCENARIOS[0]], {"alvenaria": 100},
        data_inicio="2026-11-06",
        calendario={"modo": "uteis", "feriados": ["2026-11-09"]})
    assert r["cenarios"][0]["tarefas"][0]["data_fim_exclusiva"] == "2026-11-11"


@pytest.mark.parametrize("rates,overhead", [
    ({"alvenaria": -1}, 0),
    ({"alvenaria": 100}, -3),
    ({}, 0),
])
def test_invalid_prices_rejected(rates, overhead):
    with pytest.raises(ValueError):
        comparar_cenarios_custo_prazo(TASKS, SCENARIOS, rates,
                                      custo_indireto_por_dia=overhead)


def test_missing_rate_rejected():
    with pytest.raises(ValueError, match="Falta custo"):
        comparar_cenarios_custo_prazo(TASKS, SCENARIOS, {"pedreiro": 50})


def test_duplicate_scenarios_rejected():
    with pytest.raises(ValueError, match="duplicado"):
        comparar_cenarios_custo_prazo(
            TASKS, [SCENARIOS[0], SCENARIOS[0]], {"alvenaria": 100})
