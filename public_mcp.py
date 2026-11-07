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
    if not isinstance(unidades,list) or not 1<=len(unidades)<=100 or len(objs)*len(unidades)>5000:
        raise ValueError("Informe 1-100 unidades e no maximo 5000 combinacoes.")
    if any(not isinstance(x,str) or not x.strip() or len(x.strip())>100 for x in unidades):
        raise ValueError("Unidade invalida.")
    unidades_limpas = [x.strip() for x in unidades]
    if len({x.casefold() for x in unidades_limpas}) != len(unidades_limpas):
        raise ValueError("Unidades repetidas (inclusive diferencas de espacos/maiusculas).")
    inicio=date.fromisoformat(data_inicio) if data_inicio else None
    return {**_lob(objs,unidades_limpas,data_inicio=inicio),"persistido":False}

@public_mcp.tool()
def auditar_parcelas_lob_cpm(
    atividades: list[dict], locais: list[dict], parcelas: list[dict]
) -> dict:
    """Audita parcelas com janelas CPM ja convertidas no calendario da obra.

    Sem banco e sem corrigir datas automaticamente. Detecta local didatico,
    parcela orfa, inicio precoce, termino tardio e alerta cadencia suspeita.
    """
    from mcp_gantt_lob.models.auditoria_parcelas import (
        auditar_parcelas_lob_cpm as auditar,
    )
    return auditar(atividades, locais, parcelas)


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
def calcular_lob_com_vinculos(
    atividades: list[dict], locais: list[str], dependencias: list[dict],
    data_inicio: str | None = None, calendario: dict | None = None,
    restricoes_inicio: list[dict] | None = None,
) -> dict:
    """LOB de atividades x locais com vinculos TI/FS explicitos, equipes e calendario opcional.

    Entrada stateless: activity_id, eap_uid (opcional), duration e location_id;
    sem acesso a bancos, obra real ou outros servidores MCP.
    """
    from mcp_gantt_lob.models.lob_rede import calcular_lob_com_vinculos as calcular
    return calcular(atividades, locais, dependencias, data_inicio, calendario, restricoes_inicio)



@public_mcp.tool()
def nivelar_recursos_com_calendario(
    atividades: list[dict], capacidades: dict[str, int],
    dependencias: list[dict] | None = None,
    data_inicio: str | None = None, calendario: dict | None = None,
) -> dict:
    """Simula recursos renovaveis com capacidades, vinculos TI e calendario comum.

    Entrada por payload, sem acesso ou alteracao de obras e baselines.
    Nao garante otimo de prazo/custo; no modo uteis exige dias inteiros.
    """
    from mcp_gantt_lob.models.resource_calendar import nivelar_recursos_com_calendario as calcular
    return calcular(atividades, capacidades, dependencias, data_inicio, calendario)



@public_mcp.tool()
def comparar_cenarios_custo_prazo(
    atividades: list[dict], cenarios: list[dict],
    custos_por_recurso_dia: dict[str, float],
    custo_indireto_por_dia: float = 0,
    dependencias: list[dict] | None = None,
    data_inicio: str | None = None, calendario: dict | None = None,
    prazo_limite_dias: float | None = None,
    custos_mobilizacao_por_recurso: dict[str, float] | None = None,
    custos_ociosidade_por_recurso_dia: dict[str, float] | None = None,
) -> dict:
    """Compara cenarios de capacidade por prazo e custo informado pelo usuario.

    Sem cotacao automatica, sem otimizacao global, sem acesso a baselines.
    Custos de mobilizacao/ociosidade opcionais e explicitos; sem precos presumidos.
    """
    from mcp_gantt_lob.models.resource_cost_scenarios import comparar_cenarios_custo_prazo as calcular
    return calcular(atividades, cenarios, custos_por_recurso_dia,
                   custo_indireto_por_dia, dependencias, data_inicio, calendario,
                   prazo_limite_dias, custos_mobilizacao_por_recurso,
                   custos_ociosidade_por_recurso_dia)


@public_mcp.tool()
def nivelar_frentes_de_trabalho(
    atividades: list[dict], capacidades_recursos: dict[str, int],
    capacidades_frentes: dict[str, int],
    dependencias: list[dict] | None = None,
    data_inicio: str | None = None, calendario: dict | None = None,
) -> dict:
    """Simula atividades por local com limite de equipes simultaneas por frente.

    Input: atividades com id/duracao_dias/local_id/recursos e ocupacao_frente
    opcional; 100% in-memory, sem consultar obras ou alterar baselines.
    """
    from mcp_gantt_lob.models.physical_fronts import nivelar_frentes_de_trabalho as calcular
    return calcular(atividades, capacidades_recursos, capacidades_frentes,
                   dependencias, data_inicio, calendario)


@public_mcp.tool()
def nivelar_calendarios_por_equipe(
    atividades: list[dict],
    capacidades_recursos: dict[str, int],
    calendarios_recursos: dict[str, dict],
    data_inicio: str,
    dependencias: list[dict] | None = None,
    capacidades_frentes: dict[str, int] | None = None,
) -> dict:
    """Programa atividades em dias produtivos comuns a cada equipe alocada.

    Aceita calendarios explicitos por recurso (dias_semana e feriados), limites
    de capacidade e opcionalmente slots fisicos por local_id. Sem banco ou
    alteracao de baselines; dias produtivos inteiros, sem horas/turnos.
    """
    from mcp_gantt_lob.models.team_calendars import nivelar_calendarios_por_equipe as calcular
    return calcular(atividades, capacidades_recursos, calendarios_recursos,
                   data_inicio, dependencias, capacidades_frentes)


@public_mcp.tool()
def comparar_cenarios_equipes_frentes(
    atividades: list[dict],
    cenarios: list[dict],
    calendarios_recursos: dict[str, dict],
    custos_por_recurso_dia: dict[str, float],
    data_inicio: str,
    custo_indireto_por_dia_corrido: float = 0,
    dependencias: list[dict] | None = None,
    prazo_limite_dias_corridos: int | None = None,
    custos_mobilizacao_por_recurso: dict[str, float] | None = None,
    custos_ociosidade_por_recurso_dia: dict[str, float] | None = None,
) -> dict:
    """Compara cenarios informados com calendarios por equipe e frentes fisicas.

    Cada cenario informa nome, capacidades_recursos e capacidades_frentes
    opcionais. Ociosidade usa dias disponiveis do proprio calendario,
    indireto usa dias civis. Sem consulta a obras, precos ou baselines.
    """
    from mcp_gantt_lob.models.team_front_cost_scenarios import comparar_cenarios_equipes_frentes as calcular
    return calcular(atividades, cenarios, calendarios_recursos,
                   custos_por_recurso_dia, data_inicio,
                   custo_indireto_por_dia_corrido, dependencias,
                   prazo_limite_dias_corridos,
                   custos_mobilizacao_por_recurso,
                   custos_ociosidade_por_recurso_dia)


@public_mcp.tool()
def listar_temas()->list[str]:
    """Lista os temas disponiveis no Gantt, sem acessar historico de exports."""
    return ["ocean","slate","forest","amber","crimson","midnight","royal_purple","teal"]

public_app=public_mcp.http_app(path="/mcp",stateless_http=True,json_response=True)
