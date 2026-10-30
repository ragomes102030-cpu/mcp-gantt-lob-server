"""P4 deterministic adapter tests with a hand-referenced fictitious project.

Injected tools are test doubles. Real MCP e2e lives in the separate
scripts/clients/arquimedes_orchestrator_smoke.py CI workflow.
"""
from __future__ import annotations
import asyncio
from copy import deepcopy
from datetime import date, timedelta
from math import ceil

import pytest

from mcp_gantt_lob.arquimedes_orchestrator import IntegracaoBloqueada, executar_fluxo
from mcp_gantt_lob.models.lob_rede import calcular_lob_com_vinculos


def _input():
    return {
      "project_id":"FICTICIO-P4","schema_version":"1.0",
      "eap_nodes":[{"eap_id":"1","eap_uid":"ROOT","nivel":1,"parent_id":None},
        {"eap_id":"1.1","eap_uid":"U-A","nivel":2,"parent_id":"1"},
        {"eap_id":"1.2","eap_uid":"U-B","nivel":2,"parent_id":"1"}],
      "locais":["P01","P02"],
      "atividades":[
        {"activity_id":"A","eap_uid":"U-A","quantidade":20,"produtividade":10,
         "unidade":"m2","unidade_produtividade":"m2","fonte":"sintetica",
         "responsavel":"Equipe A","criterio_aceite":"medicao"},
        {"activity_id":"B","eap_uid":"U-B","quantidade":30,"produtividade":10,
         "unidade":"m2","unidade_produtividade":"m2","fonte":"sintetica",
         "responsavel":"Equipe B","criterio_aceite":"medicao"}],
      "dependencias":[
        {"predecessora_id":"A","predecessora_local":"P01","sucessora_id":"B","sucessora_local":"P01"},
        {"predecessora_id":"A","predecessora_local":"P02","sucessora_id":"B","sucessora_local":"P02"}],
      "data_inicio":"2026-11-02",
      "calendario":{"modo":"uteis","calendar_id":"FICTICIO-5D",
                    "dias_semana":[0,1,2,3,4],"feriados":["2026-11-03"]}
    }


def _workday(n):
    d=date(2026,11,2)
    count=0
    while True:
        if d.weekday()<5 and d!=date(2026,11,3):
            if count==n:return d.isoformat()
            count+=1
        d+=timedelta(days=1)


def _tools(*,tamper=False,offline=False):
    async def call(motor,tool,args):
        if offline and motor=="cronograma":
            raise ConnectionError("outage")
        if tool=="validar_estrutura_eap":
            return {"ok":True,"total_nos":len(args["nos"]),"persistido":False}
        if tool=="avaliar_evidencia_eap":
            return {"total":len(args["itens"]),"lacunas":[],"persistido":False}
        if tool=="calcular_duracao_com_evidencia":
            return {"duracaoDias":ceil(args["quantidade"]/args["produtividade"]),
                    "persistido":False}
        if tool=="calcular_cpm_com_calendario":
            # Independent, hand-calculated reference for the two-pavement
            # graph. Do not reuse LOB's recurrence or CPM engine.
            expected={"A::P01":(0,2),"A::P02":(2,4),
                      "B::P01":(2,5),"B::P02":(5,8)}
            assert {x["id"] for x in args["atividades"]}==set(expected)
            assert len(args["dependencias"])==4
            return {"valid":True,"persistido":False,
              "duracao_projeto_dias":8,"atividades":[
                {"id":ident,"ES":es+1 if tamper and ident=="B::P02" else es,
                 "EF":ef,"data_inicio":_workday(es),
                 "data_fim_exclusiva":_workday(ef)}
                for ident,(es,ef) in expected.items()]}
        if tool=="calcular_lob_com_vinculos":
            return {**calcular_lob_com_vinculos(
                args["atividades"],args["locais"],args["dependencias"],
                args.get("data_inicio"),args.get("calendario")),"persistido":False}
        raise AssertionError("Unknown tool called: "+tool)
    return call


def test_uid_propagation_and_math_reconciliation():
    value=asyncio.run(executar_fluxo(_input(),_tools()))
    assert value["status"]=="PASSOU" and value["persistido"] is False
    assert value["total_tarefas"]==4
    assert value["duracoes_por_atividade"]=={"A":2,"B":3}
    assert value["mapa_tarefas"]["A::P01"]["eap_uid"]=="U-A"
    assert value["mapa_tarefas"]["B::P02"]["eap_uid"]=="U-B"
    assert value["cpm"]["duracao_projeto_dias"]==value["lob"]["duracao_total_dias"]==8
    assert value["divergencias"]==[]
    assert value["calendar_id"]=="FICTICIO-5D"


@pytest.mark.parametrize("mutator", [
    lambda p:p["atividades"][0].update(eap_uid="UNKNOWN"),
    lambda p:p["atividades"][0].update(eap_uid="ROOT"),
    lambda p:p["eap_nodes"][2].update(eap_uid="U-A"),
    lambda p:p["atividades"][1].update(activity_id="A"),
    lambda p:p.update(locais=["P01","P01"]),
    lambda p:p["atividades"][1].update(fonte=""),
    lambda p:p["dependencias"][0].update(tipo="II"),
    lambda p:p["dependencias"][0].update(predecessora_local="P99"),
    lambda p:p["atividades"][0].update(produtividade=0),
    lambda p:p.update(restricoes_inicio=[{"activity_id":"A","location_id":"P01","inicio_minimo_dia":3}]),
])
def test_fail_closed_on_bad_id_evidence_or_unsupported_network(mutator):
    data=_input()
    mutator(data)
    with pytest.raises(IntegracaoBloqueada):
        asyncio.run(executar_fluxo(data,_tools()))


def test_reject_wrong_math_despite_valid_http_payload():
    with pytest.raises(IntegracaoBloqueada,match="divergem"):
        asyncio.run(executar_fluxo(_input(),_tools(tamper=True)))


def test_no_fallback_during_mcp_outage():
    with pytest.raises(IntegracaoBloqueada,match="indisponivel"):
        asyncio.run(executar_fluxo(_input(),_tools(offline=True)))


def test_input_not_mutated():
    data=_input();before=deepcopy(data)
    asyncio.run(executar_fluxo(data,_tools()))
    assert data==before
