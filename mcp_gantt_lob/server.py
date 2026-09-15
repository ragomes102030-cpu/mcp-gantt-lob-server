"""
mcp_gantt_lob/server.py
~~~~~~~~~~~~~~~~~~~~~~~~
Servidor FastMCP do mcp-gantt-lob-server.

Segue o padrão de segurança já validado no mcp-cronograma-server (allowed
hosts explícito, proteção de DNS rebinding mantida ativa), mas usando a
API atual do pacote `fastmcp` standalone (v4.x) — o pacote `mcp` (SDK
oficial, v2.x no ambiente do Render) renomeou FastMCP para MCPServer e
mudou a estrutura interna, então o import correto é `from fastmcp import
FastMCP`, NÃO `from mcp.server.fastmcp import FastMCP`. Nessa versão,
`allowed_hosts` vai direto no `.run()`, não mais num objeto
TransportSecuritySettings passado ao construtor.
"""
from __future__ import annotations

import os
from typing import Any, Callable

from fastmcp import FastMCP

from .models import db
from .models.gantt import atividade_from_dict, gerar_gantt_base64
from .models.lob import AtividadeLOB, balancear_ritmos, calcular_linha_balanco as calcular_lob, dimensionar_equipes

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "mcp-gantt-lob-server.onrender.com").split(",")

db.init_db()  # nunca levanta exceção — ver models/db.py

mcp = FastMCP(
    name="mcp-gantt-lob-server",
    instructions=(
        "Especialista em geração de Gantt profissional (.xlsx) e em Linha de "
        "Balanço (LOB), seguindo a metodologia de Aldo Dórea Mattos. Este MCP "
        "é STATELESS: receba os dados já calculados no payload de cada chamada "
        "(datas do CPM, progresso realizado — tipicamente do mcp-cronograma-server). "
        "Para Gantt: chame gerar_gantt. Para obras com unidades repetitivas "
        "(andares, casas, trechos de rodovia): use calcular_linha_balanco em vez "
        "de tratar cada unidade como atividade separada no cronograma — ela já "
        "calcula início/fim por unidade e sinaliza risco_interferencia (equipe "
        "mais rápida esperando a de trás). Se aparecer risco_interferencia=True, "
        "chame balancear_ritmos para ver como corrigir (mudar nº de equipes de "
        "qual atividade) antes de gerar o Gantt final."
    ),
    mask_error_details=True,  # auditoria: sem auth neste MCP, evita vazar
    # stack trace/paths internos pra quem mandar payload malformado de propósito.
)


def _seguro(fn: Callable[[], Any]) -> Any:
    """Converte qualquer exceção em ``{"erro": "..."}`` em vez de deixar
    propagar como erro de protocolo MCP — mesmo contrato de resposta usado
    no mcp-eap-server e no mcp-cronograma-server, pra um agente que orquestra
    os três MCPs não precisar tratar formatos de erro diferentes por serviço.
    """
    try:
        return fn()
    except Exception as exc:
        return {"erro": str(exc)}


@mcp.tool()
def gerar_gantt(
    project_name: str,
    atividades: list[dict],
    tema: str = "ocean",
    cor_marca: str | None = None,
) -> dict:
    """
    Gera um Gantt profissional em .xlsx a partir de atividades já calculadas.

    Cada item de `atividades` deve ter:
        - nome (str)
        - secao (str) — agrupamento (ex: "Fundação", "Estrutura")
        - data_inicio (str "YYYY-MM-DD")
        - data_fim_planejada (str "YYYY-MM-DD")
        - progresso (float, 0-100)
        - data_fim_prevista_real (str "YYYY-MM-DD", opcional) — se a atividade
          estiver atrasada e já houver uma nova previsão
        - critico (bool, opcional) — folga zero no CPM

    `tema`: um dos temas prontos (ocean, slate, forest, amber, crimson,
    midnight, royal_purple, teal). Ignorado se `cor_marca` for informado.
    `cor_marca`: hex sem '#' (ex: "1F4E78") pra gerar paleta a partir da
    cor da marca/empresa.

    Retorna dict com `filename` e `xlsx_base64` (decodificar e salvar como
    .xlsx no cliente), ou `{"erro": "..."}` em caso de falha (ex.: lista
    vazia, data em formato errado, atividade sem campo obrigatório).
    """
    def _executar() -> dict:
        atividades_obj = [atividade_from_dict(a) for a in atividades]
        xlsx_b64 = gerar_gantt_base64(project_name, atividades_obj, tema=tema, cor_marca=cor_marca)
        db.registrar_export(project_name, tema, cor_marca, len(atividades_obj))
        return {
            "filename": f"{project_name.replace(' ', '_')}_gantt.xlsx",
            "xlsx_base64": xlsx_b64,
        }

    return _seguro(_executar)


@mcp.tool()
def listar_exports(limit: int = 50) -> list[dict] | dict:
    """Lista o histórico de exports de Gantt já gerados (auditoria).

    Retorna `{"erro": "..."}` se o log Turso não estiver configurado ou
    inacessível — nunca derruba a chamada.
    """
    return _seguro(lambda: db.listar_exports(limit=limit))


@mcp.tool()
def listar_temas() -> list[str]:
    """Lista os temas de cor prontos disponíveis para gerar_gantt."""
    return ["ocean", "slate", "forest", "amber", "crimson", "midnight", "royal_purple", "teal"]


def _atividades_lob_from_dicts(atividades: list[dict]) -> list[AtividadeLOB]:
    return [
        AtividadeLOB(
            nome=a["nome"],
            tempo_unitario=float(a["tempo_unitario"]),
            numero_equipes=int(a.get("numero_equipes", 1)),
            pulmao_dias=float(a.get("pulmao_dias", 0)),
        )
        for a in atividades
    ]


@mcp.tool()
def calcular_linha_balanco(
    atividades: list[dict],
    unidades: list[str],
    data_inicio: str | None = None,
) -> dict:
    """
    Calcula a Linha de Balanço (Cap. 20 do Mattos): início/fim de cada
    atividade em cada unidade de repetição (andar, casa, trecho...).

    `atividades` na ORDEM de execução (a [i] é predecessora da [i+1] na
    mesma unidade). Cada item:
        - nome (str)
        - tempo_unitario (float) — dias para 1 equipe fazer 1 unidade
        - numero_equipes (int, opcional, default 1) — reduz o tempo de
          ritmo (tr = tempo_unitario / numero_equipes)
        - pulmao_dias (float, opcional, default 0) — espera mínima extra
          além da predecessora, na mesma unidade

    `unidades`: lista ordenada de unidades de repetição, ex.:
        ["Casa 1", "Casa 2", "Casa 3"] ou ["Pav. 1", ..., "Pav. 10"].

    `data_inicio` (str "YYYY-MM-DD", opcional): se informado, cada
    unidade também vem com data_inicio/data_fim reais (dias corridos —
    não considera calendário de dias úteis nesta v1).

    Retorna, por atividade: ritmo (dias/unidade), espera_total_dias e
    `risco_interferencia` (True = a equipe ficou parada esperando a
    predecessora em algum ponto — ritmo mais rápido que ela, vale
    balancear). Ou `{"erro": "..."}` em caso de falha (ex.: lista vazia,
    unidade duplicada, tempo_unitario <= 0).
    """
    from datetime import date as _date

    def _executar() -> dict:
        atividades_obj = _atividades_lob_from_dicts(atividades)
        data_inicio_obj = _date.fromisoformat(data_inicio) if data_inicio else None
        return calcular_lob(atividades_obj, unidades, data_inicio=data_inicio_obj)

    return _seguro(_executar)


@mcp.tool()
def balancear_ritmos_lob(atividades: list[dict]) -> dict:
    """
    Cap. 20.4 do Mattos (Balanceamento das operações): compara o ritmo de
    cada atividade com o da atividade imediatamente anterior e sugere
    como igualar — mudando o nº de equipes da atividade que está causando
    risco de interferência (equipe parada esperando).

    `atividades`: mesmo formato de `calcular_linha_balanco`, na mesma
    ORDEM de execução.

    Quando há risco (sucessora mais rápida que a predecessora), retorna
    as duas formas de corrigir: reduzir a equipe da sucessora (se der pra
    chegar a >= 1 equipe) ou aumentar a equipe da predecessora pra
    acelerá-la. Quando não há risco (sucessora igual ou mais lenta —
    configuração seguro segundo o método), não sugere mudança nenhuma.
    """
    def _executar() -> dict:
        atividades_obj = _atividades_lob_from_dicts(atividades)
        return balancear_ritmos(atividades_obj)

    return _seguro(_executar)


@mcp.tool()
def dimensionar_equipes_lob(tempo_unitario: float, ritmo_desejado: float) -> dict:
    """
    Cap. 20.5 do Mattos (Dimensionamento): quantas equipes uma atividade
    precisa pra atingir um ritmo desejado (dias por unidade), dado quanto
    tempo 1 equipe leva pra fazer 1 unidade sozinha.

    Ex.: se 1 equipe leva 6 dias por casa e você quer entregar 1 casa a
    cada 2 dias (ritmo_desejado=2), retorna 3 equipes.
    """
    return _seguro(lambda: {"numero_equipes": dimensionar_equipes(tempo_unitario, ritmo_desejado)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=port,
        allowed_hosts=ALLOWED_HOSTS,
    )
