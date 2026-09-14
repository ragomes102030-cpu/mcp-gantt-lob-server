# Notas para retomar este repositório

- Baseado na lib `xlsx-gantt` v0.2.3 (MIT), validada manualmente antes
  de virar código: gera .xlsx real via openpyxl, aceita múltiplos
  DateRange coloridos por tarefa (usado para o trecho de atraso),
  progress vira databar nativa, marco = DateRange com start==end.
- Agrupamento colapsável (expand/collapse por seção) NÃO é nativo da
  lib — é pós-processado em `_aplicar_agrupamento` via
  `ws.row_dimensions[n].outlineLevel = 1` (openpyxl). Cabeçalho da
  lib ocupa sempre as 3 primeiras linhas; dados começam na linha 4 —
  se a lib mudar isso em versão futura, esse offset quebra.
- Regras de cor por status estão centralizadas no topo de
  `models/gantt.py` (COR_CONCLUIDA, COR_EM_RISCO, COR_ATRASADA) —
  ainda não uso COR_EM_RISCO de verdade na lógica (`_status_ranges`
  só decide concluída/planejada/atrasada); falta regra de "em risco"
  (perto do prazo, progresso abaixo do esperado mas ainda não venceu).
- Pendente (v1.1, documentado no README): Linha de Balanço; caminho
  crítico destacado (usar `critico` do AtividadeInput, hoje só é
  recebido e ignorado); linha do "hoje" no calendário; coluna de
  recursos/equipe via `resource_names`/`annotations` da lib; legenda
  automática de cores.
- Ainda não testado: `gerar_gantt_base64` dentro de uma chamada real
  de tool MCP via protocolo (só testei a função Python direto). Rodar
  `mcp.run()` local e testar com um cliente MCP antes do deploy.
- Autenticação: mesma decisão dos outros MCPs — deixado para depois.
