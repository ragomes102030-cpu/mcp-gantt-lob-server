"""Stateless engineering MCP orchestration adapter.

This module does NOT run inside an MCP server and never writes production
data. It orchestrates three independent public MCP endpoints supplied via
an asynchronous call(motor, tool, arguments) callback. Fail-closed.
"""
from __future__ import annotations

import math
from collections import defaultdict


class IntegracaoBloqueada(ValueError):
    pass


def _required_id(value, campo):
    if not isinstance(value, str) or not 0 < len(value.strip()) <= 48 or "::" in value:
        raise IntegracaoBloqueada(f"{campo}: ID ausente, longo demais ou com separador reservado")
    return value.strip()


def _id_tarefa(atividade, local):
    return f"{atividade}::{local}"


def _validar(pedido):
    if not isinstance(pedido, dict) or pedido.get("schema_version") != "1.0":
        raise IntegracaoBloqueada("schema_version 1.0 obrigatorio")
    projeto = _required_id(pedido.get("project_id"), "project_id")
    nos = pedido.get("eap_nodes")
    atividades = pedido.get("atividades")
    locais = pedido.get("locais")
    deps = pedido.get("dependencias")
    if not isinstance(nos, list) or not 1 <= len(nos) <= 150:
        raise IntegracaoBloqueada("eap_nodes precisa ter 1..150 nos")
    if not isinstance(atividades, list) or not 1 <= len(atividades) <= 50:
        raise IntegracaoBloqueada("atividades precisa ter 1..50 registros")
    if not isinstance(locais, list) or not 1 <= len(locais) <= 100:
        raise IntegracaoBloqueada("locais precisa ter 1..100 registros")
    if not isinstance(deps, list) or len(deps) > 400:
        raise IntegracaoBloqueada("dependencias ausentes ou acima de 400")
    unique_locations = [_required_id(v,"location_id") for v in locais]
    if len(set(x.casefold() for x in unique_locations)) != len(unique_locations):
        raise IntegracaoBloqueada("location_id duplicado")
    nodes_by_uid = {}
    eap_codes = set()
    for n in nos:
        if not isinstance(n, dict):
            raise IntegracaoBloqueada("EAP contem no nao objeto")
        uid = _required_id(n.get("eap_uid"), "eap_uid")
        code = _required_id(n.get("eap_id"), "eap_id")
        if uid in nodes_by_uid or code in eap_codes:
            raise IntegracaoBloqueada("eap_uid/eap_id duplicado")
        nodes_by_uid[uid] = n
        eap_codes.add(code)
    parents = {str(x.get("parent_id")) for x in nos if x.get("parent_id")}
    leaf_uid = {uid for uid, n in nodes_by_uid.items() if n["eap_id"] not in parents}
    activ_map = {}
    scope = []
    for a in atividades:
        if not isinstance(a, dict):
            raise IntegracaoBloqueada("atividade invalida")
        ident = _required_id(a.get("activity_id"), "activity_id")
        uid = _required_id(a.get("eap_uid"), "eap_uid")
        if ident in activ_map or uid not in leaf_uid:
            raise IntegracaoBloqueada("atividade duplicada ou eap_uid nao e folha valida da EAP")
        chosen = a.get("locais_atividade", unique_locations)
        if (not isinstance(chosen, list) or not chosen
            or len(set(chosen)) != len(chosen) or any(x not in unique_locations for x in chosen)):
            raise IntegracaoBloqueada("locais_atividade inexistentes ou duplicados")
        crew = _required_id(a.get("equipe_id", ident), "equipe_id")
        squads = a.get("numero_equipes", 1)
        if type(squads) is not int or not 1 <= squads <= 100:
            raise IntegracaoBloqueada("numero_equipes exige inteiro 1..100")
        # All durations are derived from evidence, never supplied by an LLM.
        for field in ("quantidade", "produtividade"):
            v = a.get(field)
            if type(v) not in (int, float) or not math.isfinite(v) or v <= 0:
                raise IntegracaoBloqueada(f"{ident}: {field} positivo e finito obrigatorio")
        if not a.get("unidade") or not a.get("unidade_produtividade"):
            raise IntegracaoBloqueada(f"{ident}: unidade explicita obrigatoria")
        for field in ("fonte", "responsavel", "criterio_aceite"):
            if not isinstance(a.get(field), str) or not a[field].strip():
                raise IntegracaoBloqueada(f"{ident}: {field} ausente")
        activ_map[ident] = {**a,"equipe_id":crew,"numero_equipes":squads,"locais_atividade":chosen}
        scope.append(a)
    if len(activ_map)*len(unique_locations)>2000:
        raise IntegracaoBloqueada("mais de 2000 tarefas")
    if not isinstance(pedido.get("data_inicio"), str) or not isinstance(pedido.get("calendario"), dict):
        raise IntegracaoBloqueada("data_inicio e calendario explicitos sao obrigatorios")
    if pedido.get("restricoes_inicio"):
        raise IntegracaoBloqueada("restricoes_inicio ainda nao suportadas pelo adaptador CPM/LOB conjunto")
    return projeto,nos,activ_map,unique_locations,deps,scope


async def executar_fluxo(pedido, call):
    """Run complete traceable EAP -> evidence -> CPM -> LOB cross-check.

    `call` is injected (MCP client, simulator or test double). Results
    must be real structured results with persistido=False.
    """
    projeto,nos,act,locais,deps,scope = _validar(pedido)

    async def seguro(motor, nome, args):
        try:
            result = await call(motor,nome,args)
        except Exception as exc:
            raise IntegracaoBloqueada(f"{motor}/{nome}: indisponivel ou erro: {type(exc).__name__}") from exc
        if not isinstance(result,dict) or result.get("persistido") is not False:
            raise IntegracaoBloqueada(f"{motor}/{nome}: resultado sem comprovacao stateless")
        return result

    eap = await seguro("eap","validar_estrutura_eap",{"nos":nos})
    if eap.get("ok") is not True or eap.get("total_nos") != len(nos):
        raise IntegracaoBloqueada("EAP estrutural reprovada")
    evidence = await seguro("eap","avaliar_evidencia_eap",{"itens":scope})
    if evidence.get("lacunas") or evidence.get("total") != len(act):
        raise IntegracaoBloqueada("Evidencia de escopo incompleta")
    duration = {}
    for ident, item in act.items():
        value = await seguro("cronograma","calcular_duracao_com_evidencia",{
            "quantidade":item["quantidade"],"produtividade":item["produtividade"],
            "unidade":item["unidade"],"unidade_produtividade":item["unidade_produtividade"],
            "fonte":item["fonte"]})
        days = value.get("duracaoDias")
        if type(days) is not int or not 0 < days <= 1000000:
            raise IntegracaoBloqueada(f"{ident}: duracao sem evidencia deterministica valida")
        duration[ident] = days

    canonical=[]
    crew_chains=defaultdict(list)
    task_map={}
    lob_activities=[]
    for ident,a in act.items():
        lob_activities.append({"activity_id":ident,"eap_uid":a["eap_uid"],
            "nome":a.get("nome",ident),"duracao_dias":duration[ident],
            "numero_equipes":a["numero_equipes"],"equipe_id":a["equipe_id"],
            "locais_atividade":a["locais_atividade"]})
        for local in locais:
            if local not in a["locais_atividade"]: continue
            key=_id_tarefa(ident,local)
            task_map[key]={"activity_id":ident,"location_id":local,
                           "eap_uid":a["eap_uid"],"project_id":projeto,
                           "quantity":a["quantidade"],"unit":a["unidade"]}
            crew_chains[a["equipe_id"]].append(key)
            canonical.append({"id":key,"duracao_dias":duration[ident]/a["numero_equipes"]})
    if len(canonical)>150:
        raise IntegracaoBloqueada("CPM publico limita 150 tarefas; lote nao pode ser fragmentado sem revisao")

    edges={}
    def link(p,s,lag):
        if p not in task_map or s not in task_map or p==s:
            raise IntegracaoBloqueada("dependencia referencia tarefa inexistente ou auto-referencia")
        if not isinstance(lag,(float,int)) or not math.isfinite(lag) or lag<0:
            raise IntegracaoBloqueada("lag TI deve ser nao negativo e finito")
        if (p,s) in edges and edges[(p,s)] != lag:
            raise IntegracaoBloqueada("lags contraditorios entre tarefas")
        edges[p,s]=lag
    for d in deps:
        if not isinstance(d,dict) or d.get("tipo","TI")!="TI":
            raise IntegracaoBloqueada("integracao LOB requer apenas TI; CPM isolado suporta quatro tipos")
        link(_id_tarefa(_required_id(d.get("predecessora_id"),"predecessora_id"),
                        _required_id(d.get("predecessora_local"),"predecessora_local")),
             _id_tarefa(_required_id(d.get("sucessora_id"),"sucessora_id"),
                        _required_id(d.get("sucessora_local"),"sucessora_local")),
             d.get("lag_dias",0))
    for chain in crew_chains.values():
        for p,s in zip(chain,chain[1:]):
            if (p,s) not in edges:
                link(p,s,0)
    cpm = await seguro("cronograma","calcular_cpm_com_calendario",{
        "atividades":canonical,
        "dependencias":[{"predecessora_id":p,"sucessora_id":s,"tipo":"TI",
                          "lag_dias":lag} for (p,s),lag in edges.items()],
        "data_inicio":pedido["data_inicio"],"calendario":pedido["calendario"]})
    if cpm.get("valid") is not True or len(cpm.get("atividades",[]))!=len(canonical):
        raise IntegracaoBloqueada("CPM invalido ou numero de tarefas inesperado")
    lob = await seguro("lob","calcular_lob_com_vinculos",{
        "atividades":lob_activities,"locais":locais,
        "dependencias":deps,"data_inicio":pedido["data_inicio"],
        "calendario":pedido["calendario"]})
    if len(lob.get("tarefas",[]))!=len(task_map):
        raise IntegracaoBloqueada("LOB gerou numero diferente de tarefas")
    cpm_rows={r["id"]:r for r in cpm["atividades"]}
    observed=set()
    for t in lob["tarefas"]:
        key=_id_tarefa(t["activity_id"],t["location_id"])
        if key in observed or key not in task_map or key not in cpm_rows:
            raise IntegracaoBloqueada("LOB: tarefa ausente, duplicada ou desconhecida")
        observed.add(key)
        if t.get("eap_uid")!=task_map[key]["eap_uid"]:
            raise IntegracaoBloqueada("LOB: eap_uid alterado")
        row=cpm_rows[key]
        if abs(row["ES"]-t["inicio_dia"])>1e-6 or abs(row["EF"]-t["fim_dia"])>1e-6:
            raise IntegracaoBloqueada(f"CPM/LOB divergem em {key}: ES/EF")
        if (row.get("data_inicio")!=t.get("data_inicio")
            or row.get("data_fim_exclusiva")!=t.get("data_fim_exclusiva")):
            raise IntegracaoBloqueada(f"CPM/LOB divergem em {key}: calendario")
    if abs(cpm["duracao_projeto_dias"]-lob["duracao_total_dias"])>1e-6:
        raise IntegracaoBloqueada("CPM/LOB divergem no prazo")
    return {"status":"PASSOU","persistido":False,"project_id":projeto,
            "schema_version":"1.0","calculation_version":"arquimedes-adapter-p4",
            "calendar_id":pedido["calendario"].get("calendar_id"),
            "total_tarefas":len(task_map),"duracoes_por_atividade":duration,
            "mapa_tarefas":task_map,"eap_validacao":eap,"evidencia":evidence,
            "cpm":cpm,"lob":lob,"divergencias":[]}
