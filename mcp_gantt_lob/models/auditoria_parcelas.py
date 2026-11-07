"""Auditoria stateless de parcelas LOB contra janelas CPM fornecidas pelo chamador.

Nao converte dias uteis nem infere endereco/local real: a Plataforma fornece
start/end ja calculados com o calendario da obra. Sem escrita/persistencia.
"""
from __future__ import annotations
from datetime import date
from collections import defaultdict


def _date(value: object) -> date:
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("Data ISO YYYY-MM-DD obrigatoria")
    d = date.fromisoformat(value)
    if d.isoformat() != value:
        raise ValueError("Data ISO invalida")
    return d


def auditar_parcelas_lob_cpm(
    atividades: list[dict], locais: list[dict], parcelas: list[dict]
) -> dict:
    """Audita identidade da atividade, local didatico e janela CPM oficial.

    atividades: id, inicio_cpm, fim_cpm (datas civis do calendario da obra).
    locais: id, nome, didatico (bool explicito, preferencialmente).
    parcelas: activity_id, location_id, start_date, finish_date.
    """
    if not all(isinstance(x, list) for x in (atividades, locais, parcelas)):
        raise ValueError("As tres colecoes devem ser listas")
    if len(atividades) > 10000 or len(locais) > 1000 or len(parcelas) > 50000:
        raise ValueError("Limite de auditoria excedido")
    acts = {str(a["id"]): a for a in atividades}
    units = {str(l["id"]): l for l in locais}
    if len(acts) != len(atividades) or len(units) != len(locais):
        raise ValueError("IDs duplicados em atividades ou locais")
    achados = []
    grupos = defaultdict(list)
    for idx, p in enumerate(parcelas):
        aid = str(p.get("activity_id", ""))
        lid = str(p.get("location_id", ""))
        atividade = acts.get(aid)
        local = units.get(lid)
        def add(codigo: str) -> None:
            achados.append({"indice_parcela": idx, "activity_id": aid,
                            "location_id": lid, "codigo": codigo})
        if atividade is None:
            add("ATIVIDADE_ORFA")
        if local is None:
            add("LOCAL_DESCONHECIDO")
        elif local.get("didatico") is True or "didátic" in str(local.get("nome", "")).casefold() or "didatic" in str(local.get("nome", "")).casefold():
            add("LOCAL_DIDATICO")
        try:
            start, finish = _date(p.get("start_date")), _date(p.get("finish_date"))
            if start > finish:
                add("PARCELA_INVERTIDA")
            if atividade is not None:
                if start < _date(atividade.get("inicio_cpm")):
                    add("ANTES_DO_CPM")
                if finish > _date(atividade.get("fim_cpm")):
                    add("DEPOIS_DO_CPM")
        except (TypeError, ValueError):
            add("DATA_INVALIDA_OU_CPM_AUSENTE")
        grupos[aid].append(p.get("start_date"))
    # Falta de defasagem entre locais eh indicio, nao erro: equipes paralelas sao possiveis.
    alertas = [{"activity_id": aid, "codigo": "REVISAR_CADENCIA",
                "total_parcelas": len(datas)} for aid, datas in grupos.items()
               if len(datas) > 1 and len(set(datas)) == 1]
    return {"valido": not achados, "total_parcelas": len(parcelas),
            "total_bloqueios": len(achados), "achados": achados,
            "alertas": alertas, "persistido": False,
            "nota": "Datas CPM ja devem vir convertidas pelo calendario da obra; nao infere ritmos nem locais."}
