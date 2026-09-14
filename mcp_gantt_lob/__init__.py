"""
mcp_gantt_lob
~~~~~~~~~~~~~
MCP especialista em geração de Gantt (via xlsx-gantt) e Linha de Balanço
(LOB), seguindo a metodologia de Aldo Dórea Mattos.

Diferente do mcp-eap-server e mcp-cronograma-server, este MCP é STATELESS
no MVP: não persiste dados próprios em banco. Ele recebe atividades já
calculadas (tipicamente vindas do mcp-cronograma-server via prompt mestre
de orquestração) e devolve o arquivo .xlsx gerado.

Se no futuro precisar persistir (ex: cache de gráficos gerados, histórico
de exports), seguir o mesmo padrão dos outros MCPs: DB_PATH resolvido
aqui, banco Turso próprio deste serviço.
"""

DB_PATH = None  # reservado para uso futuro; ver models/ e regra de _connect()
