# mcp-gantt-lob-server

MCP especialista em geração de Gantt profissional (.xlsx) e, futuramente,
Linha de Balanço (LOB), seguindo a metodologia de Aldo Dórea Mattos
("Planejamento e Controle de Obras").

## Status: Gantt + Linha de Balanço (v1)

## Escopo
- **Gantt**: recebe atividades já calculadas (datas do CPM, progresso
  realizado — tipicamente do mcp-cronograma-server) e devolve um .xlsx
  profissional: barras planejado x atraso, progresso, marcos, seções
  colapsáveis (expand/collapse), 8 temas de cor prontos ou paleta a
  partir de cor de marca, caminho crítico destacado.
- **Linha de Balanço**: implementada seguindo o Cap. 20 do livro do
  Mattos — `calcular_linha_balanco` (início/fim por unidade de
  repetição + detecção de risco de interferência), `balancear_ritmos_lob`
  (Cap. 20.4, sugere nº de equipes pra igualar ritmos), `dimensionar_equipes_lob`
  (Cap. 20.5, quantas equipes pra atingir um ritmo desejado).

## Fora de escopo (por design)
- Monte Carlo — fica no mcp-cronograma-server (trabalha em cima de
  duração/incerteza das atividades, não é responsabilidade da camada
  de apresentação).
- Produção de equipes (produtividade, disponibilidade, custo real) —
  fica para o futuro mcp-recursos-server. Este MCP só recebe
  produtividade/nº de equipes como parâmetro simples.

## Arquitetura
Stateless no MVP — não tem banco próprio. Recebe os dados no payload da
tool a cada chamada. Se precisar de persistência no futuro (cache de
exports, histórico), seguir o padrão dos outros MCPs: banco Turso
próprio deste serviço, `_connect()` resolvendo `DB_PATH` via
`from . import DB_PATH`.

## Tools
- `gerar_gantt(project_name, atividades, tema, cor_marca)` → dict com
  `filename` e `xlsx_base64`.
- `listar_temas()` → lista de temas prontos disponíveis.
- `listar_exports(limit)` → histórico de exports (auditoria, via Turso).
- `calcular_linha_balanco(atividades, unidades, data_inicio)` → início/fim
  por unidade + `risco_interferencia` por atividade.
- `balancear_ritmos_lob(atividades)` → sugestão de nº de equipes pra
  igualar ritmo com a atividade anterior.
- `dimensionar_equipes_lob(tempo_unitario, ritmo_desejado)` → nº de
  equipes pra atingir um ritmo desejado.

## Deploy
Padrão dos outros MCPs: Render, `TransportSecuritySettings` com
`allowed_hosts` explícito e `enable_dns_rebinding_protection=True`
(nunca desativar a proteção inteira).
