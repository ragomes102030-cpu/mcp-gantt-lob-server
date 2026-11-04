"""Regression for cost/time scenarios with individual calendars and front slots."""
import pytest

from mcp_gantt_lob.models.team_front_cost_scenarios import comparar_cenarios_equipes_frentes as compare

ACTIVITIES = [
    {"id": "A", "duracao_dias": 2, "local_id": "P01",
     "recursos": {"alvenaria": 1}},
    {"id": "B", "duracao_dias": 2, "local_id": "P01",
     "recursos": {"eletrica": 1}},
]
CALENDARS = {
    "alvenaria": {"dias_semana": [0, 1, 2, 3, 4],
                  "feriados": ["2026-11-09"]},
    "eletrica": {"dias_semana": [0, 1, 2, 3, 4]},
}
COSTS = {"alvenaria": 100, "eletrica": 100}
SCENARIOS = [
    {"nome": "uma-frente", "capacidades_recursos":
     {"alvenaria": 1, "eletrica": 1}, "capacidades_frentes": {"P01": 1}},
    {"nome": "duas-frentes", "capacidades_recursos":
     {"alvenaria": 1, "eletrica": 1}, "capacidades_frentes": {"P01": 2}},
]


def _compare(**kwargs):
    return compare(ACTIVITIES, SCENARIOS, CALENDARS, COSTS,
                   "2026-11-06", **kwargs)


def test_front_capacity_drives_deadline_and_overhead():
    r = _compare(custo_indireto_por_dia_corrido=50,
                 prazo_limite_dias_corridos=5)
    one, two = r["cenarios"]
    assert one["duracao_total_dias_corridos"] == 7
    assert two["duracao_total_dias_corridos"] == 5
    assert one["data_fim_projeto_exclusiva"] == "2026-11-13"
    assert two["data_fim_projeto_exclusiva"] == "2026-11-11"
    assert (one["custo_direto"], one["custo_indireto"]) == (400, 350)
    assert (two["custo_direto"], two["custo_indireto"]) == (400, 250)
    assert r["melhor_cenario_testado"] == "duas-frentes"
    assert not one["dentro_prazo"] and two["dentro_prazo"]
    assert r["persistido"] is False


def test_idle_cost_counts_available_resource_days_only():
    r = _compare(custo_indireto_por_dia_corrido=50,
                 custos_mobilizacao_por_recurso={
                     "alvenaria": 100, "eletrica": 100},
                 custos_ociosidade_por_recurso_dia={
                     "alvenaria": 10, "eletrica": 10})
    one, two = r["cenarios"]
    assert one["disponibilidade_unidades_dia_produtivo"] == {
        "alvenaria": 4, "eletrica": 5}
    assert one["consumo_unidades_dia_produtivo"] == {
        "alvenaria": 2, "eletrica": 2}
    assert one["ociosidade_unidades_dia_produtivo"] == {
        "alvenaria": 2, "eletrica": 3}
    assert one["custo_ociosidade"] == 50
    assert one["custo_total"] == 1000
    assert two["ociosidade_unidades_dia_produtivo"] == {
        "alvenaria": 0, "eletrica": 1}
    assert two["custo_ociosidade"] == 10
    assert two["custo_total"] == 860
    assert r["melhor_cenario_testado"] == "duas-frentes"


def test_no_optional_rates_retains_zero_optional_lines():
    one, two = _compare()["cenarios"]
    assert one["custo_mobilizacao"] == one["custo_ociosidade"] == 0
    assert two["custo_mobilizacao"] == two["custo_ociosidade"] == 0
    assert one["custo_total"] == two["custo_total"] == 400


def test_deadline_infeasible_has_no_winner():
    r = _compare(prazo_limite_dias_corridos=3)
    assert r["melhor_cenario_testado"] is None
    assert all(not x["dentro_prazo"] for x in r["cenarios"])


def test_independent_floor_only_counts_actual_resource_days():
    tasks = [{**ACTIVITIES[0]}, {**ACTIVITIES[1], "local_id": "P02"}]
    scenarios = [{"nome": "pavimentos-independentes",
                  "capacidades_recursos": {"alvenaria": 1, "eletrica": 1},
                  "capacidades_frentes": {"P01": 1, "P02": 1}}]
    r = compare(tasks, scenarios, CALENDARS, COSTS, "2026-11-06",
                custo_indireto_por_dia_corrido=50)
    assert r["cenarios"][0]["duracao_total_dias_corridos"] == 5
    assert r["cenarios"][0]["custo_total"] == 650


@pytest.mark.parametrize("kw", [
    {"custos_ociosidade_por_recurso_dia": {"eletrica": -1}},
    {"custos_mobilizacao_por_recurso": {"inexistente": 10}},
    {"custo_indireto_por_dia_corrido": float("nan")},
    {"prazo_limite_dias_corridos": 1.5},
])
def test_invalid_expenses_and_deadlines_rejected(kw):
    with pytest.raises(ValueError):
        _compare(**kw)


def test_scenario_bad_calendar_or_capacity_rejected():
    with pytest.raises(ValueError):
        compare(ACTIVITIES, SCENARIOS, {"alvenaria": CALENDARS["alvenaria"]},
                COSTS, "2026-11-06")
    invalid = [{**SCENARIOS[0],
                "capacidades_frentes": {"P01": 0}}]
    with pytest.raises(ValueError):
        compare(ACTIVITIES, invalid, CALENDARS, COSTS, "2026-11-06")


def test_dependency_serializes_even_with_two_front_slots():
    deps = [{"predecessora_id": "A", "sucessora_id": "B", "tipo": "TI"}]
    r = _compare(dependencias=deps)
    assert r["cenarios"][0]["data_fim_projeto_exclusiva"] == (
        r["cenarios"][1]["data_fim_projeto_exclusiva"])
    assert r["cenarios"][0]["duracao_total_dias_corridos"] == 7
