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

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "mcp-gantt-lob-server.onrender.com").split(",")

db.init_db()  # nunca levanta exceção — ver models/db.py

mcp = FastMCP(
    name="mcp-gantt-lob-server",
    instructions=(
        "Especialista em geração de Gantt profissional (.xlsx) e, futuramente, "
        "Linha de Balanço, seguindo a metodologia de Aldo Dórea Mattos. "
        "Este MCP é STATELESS: receba as atividades já calculadas (datas do "
        "CPM, progresso realizado) tipicamente vindas do mcp-cronograma-server "
        "e chame gerar_gantt para obter o arquivo pronto em base64."
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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=port,
        allowed_hosts=ALLOWED_HOSTS,
    )
