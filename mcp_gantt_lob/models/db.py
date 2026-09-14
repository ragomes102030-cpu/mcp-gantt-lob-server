"""
mcp_gantt_lob/models/db.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Persistência mínima deste MCP: apenas um log de auditoria dos exports
gerados (não é fonte de verdade de dado de planejamento — isso mora no
mcp-eap-server / mcp-cronograma-server).

Segue as lições já aplicadas nos outros MCPs:
- _connect() resolve DB_PATH via `from . import DB_PATH` (não a
  constante local), pra não quebrar monkeypatch em testes.
- init_db() NUNCA levanta exceção — só loga e segue. Roda na importação
  do server.py, antes do uvicorn subir; um raise aqui derruba o boot.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import libsql_client

from . import gantt  # noqa: F401  (garante que o pacote models está completo)

logger = logging.getLogger(__name__)


def _connect():
    from .. import DB_PATH, TURSO_AUTH_TOKEN

    if not DB_PATH:
        raise RuntimeError(
            "TURSO_DATABASE_URL não configurada — defina a env var no serviço."
        )
    # O client sync sobre libsql:// tenta WebSocket, que falhou no handshake
    # em produção (WSServerHandshakeError 400). https:// usa o transporte
    # HTTP remoto, mais compatível com o client síncrono.
    url = DB_PATH.replace("libsql://", "https://", 1)
    return libsql_client.create_client_sync(url=url, auth_token=TURSO_AUTH_TOKEN)


def init_db() -> None:
    """Cria a tabela de log se não existir. Nunca levanta exceção."""
    try:
        client = _connect()
        client.execute(
            """
            CREATE TABLE IF NOT EXISTS export_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL,
                tema TEXT,
                cor_marca TEXT,
                n_atividades INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        client.close()
    except Exception:
        logger.exception("Falha ao inicializar/migrar o banco Turso — seguindo sem persistência de log.")


def registrar_export(project_name: str, tema: str | None, cor_marca: str | None, n_atividades: int) -> None:
    """Registra um export no log. Falha silenciosa (log de erro) — nunca
    deve impedir a tool gerar_gantt de devolver o arquivo ao usuário."""
    try:
        client = _connect()
        client.execute(
            "INSERT INTO export_log (project_name, tema, cor_marca, n_atividades, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            [project_name, tema, cor_marca, n_atividades, datetime.now(timezone.utc).isoformat()],
        )
        client.close()
    except Exception:
        logger.exception("Falha ao registrar export no log Turso — export foi gerado normalmente.")


def listar_exports(limit: int = 50) -> list[dict]:
    """Lista os últimos exports registrados (ferramenta de auditoria)."""
    client = _connect()
    rs = client.execute(
        "SELECT project_name, tema, cor_marca, n_atividades, created_at "
        "FROM export_log ORDER BY id DESC LIMIT ?",
        [limit],
    )
    client.close()
    cols = ["project_name", "tema", "cor_marca", "n_atividades", "created_at"]
    return [dict(zip(cols, row)) for row in rs.rows]
