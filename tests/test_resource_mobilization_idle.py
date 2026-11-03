"""QA of optional mobilization and idle capacity cost accounting."""
import pytest
from mcp_gantt_lob.models.resource_cost_scenarios import comparar_cenarios_custo_prazo

TASKS = [
    {"id": "A", "duracao_dias": 2, "recursos": {"pedreiro": 1}},
    {"id": "B", "duracao_dias": 2, "recursos": {"pedreiro": 1}},
]
SCENARIOS = [
    {"nome": "uma", "capacidades": {"pedreiro": 1}},
    {"nome": "duas", "capacidades": {"pedreiro": 2}},
]


def test_defaults_keep_existing_costs_and_zero_optional_lines():
    result = comparar_cenarios_custo_prazo(
        TASKS, SCENARIOS, {"pedreiro": 100}, custo_indireto_por_dia=50)
    assert [s["custo_total"] for s in result["cenarios"]] == [600, 500]
    assert all(s["custo_mobilizacao"] == s["custo_ociosidade"] == 0
               for s in result["cenarios"])


def test_mobilization_is_per_reserved_capacity_unit():
    result = comparar_cenarios_custo_prazo(
        TASKS, SCENARIOS, {"pedreiro": 100}, custo_indireto_por_dia=50,
        custos_mobilizacao_por_recurso={"pedreiro": 100})
    assert [(s["custo_mobilizacao"], s["custo_total"]) for s in result["cenarios"]] == [
        (100, 700), (200, 700)
    ]


def test_idle_units_days_include_unused_reserved_capacity():
    dependencies = [{"predecessora_id": "A", "sucessora_id": "B",
                     "tipo": "TI"}]
    result = comparar_cenarios_custo_prazo(
        TASKS, SCENARIOS, {"pedreiro": 100}, custo_indireto_por_dia=50,
        dependencias=dependencies,
        custos_mobilizacao_por_recurso={"pedreiro": 100},
        custos_ociosidade_por_recurso_dia={"pedreiro": 10},
    )
    one, two = result["cenarios"]
    assert (one["custo_direto"], one["custo_indireto"], one["custo_mobilizacao"],
            one["custo_ociosidade"], one["custo_total"]) == (400, 200, 100, 0, 700)
    assert two["ociosidade_unidades_dia"] == {"pedreiro": 4}
    assert (two["custo_direto"], two["custo_indireto"], two["custo_mobilizacao"],
            two["custo_ociosidade"], two["custo_total"]) == (400, 200, 200, 40, 840)
    assert result["melhor_cenario_testado"] == "uma"


@pytest.mark.parametrize("field,payload", [
    ("custos_mobilizacao_por_recurso", {"pedreiro": -1}),
    ("custos_ociosidade_por_recurso_dia", {"pedreiro": float("nan")}),
    ("custos_mobilizacao_por_recurso", {"guindaste": 10}),
    ("custos_ociosidade_por_recurso_dia", [10]),
])
def test_invalid_optional_rates_are_rejected(field, payload):
    with pytest.raises(ValueError):
        comparar_cenarios_custo_prazo(
            TASKS, SCENARIOS, {"pedreiro": 100}, **{field: payload})
