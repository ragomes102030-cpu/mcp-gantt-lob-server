"""Benchmark P3: work packages and locations use stable references.

Independent hand references; no real works, database, HTTP or MCP dependency.
"""
from __future__ import annotations
from datetime import date
import pytest
from mcp_gantt_lob.models.lob_rede import calcular_lob_com_vinculos


def _row(result, aid, local):
    return next(x for x in result["tarefas"] if (x["activity_id"], x["location_id"]) == (aid, local))


def _dados():
    return [
        {"activity_id":"A","nome":"Estrutura","eap_uid":"UID-101","duracao_dias":2},
        {"activity_id":"B","nome":"Alvenaria","eap_uid":"UID-102","duracao_dias":3},
    ], ["P01","P02"], [
        {"predecessora_id":"A","predecessora_local":"P01","sucessora_id":"B","sucessora_local":"P01"},
        {"predecessora_id":"A","predecessora_local":"P02","sucessora_id":"B","sucessora_local":"P02"},
    ]


def test_explicit_links_hand_reference_and_stable_ids():
    a, places, deps = _dados()
    r = calcular_lob_com_vinculos(a, places, deps, data_inicio="2026-11-02")
    assert r["persistido"] is False and r["total_tarefas"] == 4
    assert r["duracao_total_dias"] == 8
    assert [(_row(r, x, y)["inicio_dia"], _row(r, x, y)["fim_dia"])
            for x, y in [("A","P01"),("A","P02"),("B","P01"),("B","P02")]] == [
                (0,2),(2,4),(2,5),(5,8)]
    assert _row(r,"B","P02")["eap_uid"] == "UID-102"
    assert _row(r,"B","P02")["vinculos_determinantes"]


def test_service_subset_and_cross_location_dependency():
    a, _, _ = _dados()
    a[1]["locais_atividade"]=["P02"]
    deps=[{"predecessora_id":"A","predecessora_local":"P01",
           "sucessora_id":"B","sucessora_local":"P02"}]
    r = calcular_lob_com_vinculos(a,["P01","P02"],deps)
    assert r["total_tarefas"] == 3
    assert (_row(r,"B","P02")["inicio_dia"],_row(r,"B","P02")["fim_dia"]) == (2,5)


def test_shared_crew_never_overlaps_even_between_services():
    a, p, _ = _dados()
    for service in a: service["equipe_id"]="M1"
    r=calcular_lob_com_vinculos(a,p,[])
    tasks=sorted(r["tarefas"],key=lambda z:z["inicio_dia"])
    assert [(t["inicio_dia"],t["fim_dia"]) for t in tasks] == [(0,2),(2,4),(4,7),(7,10)]
    assert r["duracao_total_dias"] == 10


def test_start_constraint_and_traceable_driver():
    a,p,deps=_dados()
    r=calcular_lob_com_vinculos(a,p,deps,restricoes_inicio=[
        {"activity_id":"B","location_id":"P02","inicio_minimo_dia":9}
    ])
    assert _row(r,"B","P02")["inicio_dia"] == 9
    assert r["duracao_total_dias"] == 12


def test_weekdays_skip_holiday_and_weekend():
    a=[{"activity_id":"A","duracao_dias":1}]
    r=calcular_lob_com_vinculos(a,["P01","P02","P03"],[],
        data_inicio="2026-11-02",
        calendario={"modo":"uteis","calendar_id":"CAL-1",
                    "dias_semana":[0,1,2,3,4],"feriados":["2026-11-03"]})
    x=[_row(r,"A",p) for p in ["P01","P02","P03"]]
    assert [v["data_inicio"] for v in x] == ["2026-11-02","2026-11-04","2026-11-05"]
    assert x[2]["data_fim_exclusiva"] == "2026-11-06"
    assert r["calendar_id"] == "CAL-1"
    assert r["duracao_total_dias"] == 3


@pytest.mark.parametrize("bad_deps", [
    [{"predecessora_id":"X","predecessora_local":"P01","sucessora_id":"B","sucessora_local":"P01"}],
    [{"predecessora_id":"A","predecessora_local":"P01","sucessora_id":"B","sucessora_local":"P01","lag_dias":-1}],
    [{"predecessora_id":"A","predecessora_local":"P01","sucessora_id":"B","sucessora_local":"P01","tipo":"II"}],
    [{"predecessora_id":"A","predecessora_local":"P01","sucessora_id":"B","sucessora_local":"P01"},
     {"predecessora_id":"B","predecessora_local":"P01","sucessora_id":"A","sucessora_local":"P01"}],
])
def test_fail_closed_on_orphan_lag_type_cycle(bad_deps):
    a,_,_= _dados()
    with pytest.raises(ValueError):
        calcular_lob_com_vinculos(a,["P01"],bad_deps)


def test_no_fractional_workdays_or_mutation_of_inputs():
    a=[{"activity_id":"A","duracao_dias":1.5}]
    with pytest.raises(ValueError,match="inteiras"):
        calcular_lob_com_vinculos(a,["P01"],[],data_inicio="2026-11-02",
                                calendario={"modo":"uteis"})
    assert a == [{"activity_id":"A","duracao_dias":1.5}]


def test_calendar_requires_start_and_valid_weekdays():
    a=[{"activity_id":"A","duracao_dias":1}]
    with pytest.raises(ValueError):
        calcular_lob_com_vinculos(a,["P01"],[],calendario={"modo":"uteis"})
    with pytest.raises(ValueError):
        calcular_lob_com_vinculos(a,["P01"],[],data_inicio="2026-11-02",
                                 calendario={"modo":"uteis","dias_semana":[7]})


def test_fractional_calendar_days_preserves_subday_times():
    r=calcular_lob_com_vinculos(
      [{"activity_id":"P","duracao_dias":1,"numero_equipes":2}],
      ["P01","P02"],[],data_inicio="2026-11-02")
    assert _row(r,"P","P01")["data_hora_fim_exclusiva"] == "2026-11-02T12:00:00"
    assert _row(r,"P","P02")["data_hora_inicio"] == "2026-11-02T12:00:00"
