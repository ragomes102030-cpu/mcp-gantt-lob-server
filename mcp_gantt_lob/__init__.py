"""
mcp_gantt_lob
~~~~~~~~~~~~~
MCP especialista em geração de Gantt (via xlsx-gantt) e Linha de Balanço
(LOB), seguindo a metodologia de Aldo Dórea Mattos.

A geração do Gantt em si é stateless (recebe atividades no payload da
tool). O banco Turso deste serviço guarda apenas um HISTÓRICO de exports
(log de auditoria: quando cada .xlsx foi gerado, pra qual projeto) — não
é fonte de verdade de nenhum dado de planejamento.

Resolução de DB_PATH via env vars, mesmo padrão dos outros MCPs:
    TURSO_DATABASE_URL, TURSO_AUTH_TOKEN
"""
import os

DB_PATH = os.environ.get("TURSO_DATABASE_URL")
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN")
