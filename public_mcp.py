"""MCP publico: Linha de Balanco calculada so com payload, sem banco ou export log."""
from __future__ import annotations
import math
from datetime import date
from fastmcp import FastMCP
from mcp_gantt_lob.models.lob import (
    AtividadeLOB, calcular_linha_balanco as _lob, dimensionar_equipes as _dimensionar,
    balancear_ritmos as _balancear
)

public_mcp=FastMCP(name="arquimedes-gantt-lob-publico",
    instructions="LOB anonima em memoria, sem ler obras, exportacoes ou gravar dados.",
    mask_error_details=True)

def _validar_atividades(atividades:list[dict])->list[AtividadeLOB]:
    if not isinstance(atividades,list) or not 1<=len(atividades)<=50:
        raise ValueError("Informe 1-50 atividades.")
    nomes=[]
    result=[]
    for a in atividades:
        if not isinstance(a,dict): raise ValueError("Atividade invalida")
        nome=str(a.get("nome") or "").strip()
        if not nome or len(nome)>100 or nome in nomes: raise ValueError("Nome ausente, duplicado ou longo")
        nomes.append(nome)
        try:
            tempo=float(a["tempo_unitario"])
            pulmao=float(a.get("pulmao_dias",0))
        except (KeyError,TypeError,ValueError) as exc:
            raise ValueError("tempo_unitario/pulmao_dias ausente ou invalido") from exc
        equipes=a.get("numero_equipes",1)
        if not (math.isfinite(tempo) and 0 < tempo <= 1e6):
            raise ValueError("tempo_unitario deve ser positivo, finito e limitado")
        if not (math.isfinite(pulmao) and 0 <= pulmao <= 1e6):
            raise ValueError("pulmao_dias deve ser nao negativo, finito e limitado")
        if type(equipes) is not int or not 1<=equipes<=100:
            raise ValueError("Numero de equipes deve ser inteiro de 1 a 100")
        result.append(AtividadeLOB(nome=nome,tempo_unitario=tempo,
                                   numero_equipes=equipes,pulmao_dias=pulmao))
    return result

@public_mcp.tool()
def calcular_linha_balanco(atividades:list[dict],unidades:list[str],data_inicio:str|None=None)->dict:
    """Calcula LOB repetitiva e escadinha a partir de atividades e unidades fornecidas."""
    objs=_validar_atividades(atividades)
    if not isinstance(unidades,list) or not 1<=len(unidades)<=100 or len(objs)*len(unidades)>2000:
        raise ValueError("Informe 1-100 unidades e no maximo 2000 combinacoes.")
    if any(not isinstance(x,str) or not x.strip() or len(x.strip())>100 for x in unidades):
        raise ValueError("Unidade invalida.")
    unidades_limpas = [x.strip() for x in unidades]
    if len({x.casefold() for x in unidades_limpas}) != len(unidades_limpas):
        raise ValueError("Unidades repetidas (inclusive diferencas de espacos/maiusculas).")
    inicio=date.fromisoformat(data_inicio) if data_inicio else None
    return {**_lob(objs,unidades_limpas,data_inicio=inicio),"persistido":False}

@public_mcp.tool()
def balancear_ritmos_lob(atividades:list[dict])->dict:
    """Compara ritmos sucessivos sem alterar equipes de qualquer obra."""
    return {**_balancear(_validar_atividades(atividades)),"persistido":False}

@public_mcp.tool()
def dimensionar_equipes_lob(tempo_unitario:float,ritmo_desejado:float)->dict:
    """Equipes = teto(tempo unitario / ritmo desejado), em dias por unidade."""
    if not all(math.isfinite(v) and 0<v<=1e6 for v in (tempo_unitario,ritmo_desejado)):
        raise ValueError("Tempos devem ser positivos e finitos.")
    return {"numero_equipes":_dimensionar(tempo_unitario,ritmo_desejado),"persistido":False}

@public_mcp.tool()
def listar_temas()->list[str]:
    """Lista os temas disponiveis no Gantt, sem acessar historico de exports."""
    return ["ocean","slate","forest","amber","crimson","midnight","royal_purple","teal"]

public_app=public_mcp.http_app(path="/mcp",stateless_http=True,json_response=True)
