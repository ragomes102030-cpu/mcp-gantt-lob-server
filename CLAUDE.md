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
- Pendente: linha do "hoje" no calendário; coluna de recursos/equipe via
  `resource_names`/`annotations` da lib; legenda automática de cores;
  regra de "em risco" (COR_EM_RISCO declarada mas não usada em
  `_status_ranges` — falta a lógica de "perto do prazo, progresso
  abaixo do esperado, mas ainda não venceu").
- RESOLVIDO (auditoria): caminho crítico agora É destacado — atividade
  com `critico=True` fica em negrito + borda vermelha na coluna "Task"
  (`_marcar_criticas` em `models/gantt.py`). Attention: a coluna do
  nome da tarefa é a 2 ("Task"), não a 1 ("Activity" = nome da seção,
  só preenchido na primeira linha do grupo) — confundir as duas foi o
  primeiro erro da correção, testado e corrigido antes de commitar.
- RESOLVIDO: Linha de Balanço implementada (`models/lob.py`,
  `calcular_linha_balanco`/`balancear_ritmos_lob`/`dimensionar_equipes_lob`
  em `server.py`). Recorrência: `inicio(atividade, n) = max(fim(predecessora,
  n) + pulmão, fim(atividade, n-1))` — a mesma equipe não pode estar em
  duas unidades ao mesmo tempo, e a unidade seguinte só libera quando a
  predecessora terminar ali. `risco_interferencia` (Cap. 20.4) é True
  quando a sucessora é mais rápida que a predecessora — a métrica
  `espera_dias` só conta a partir da 2ª unidade (n>=1); contar a 1ª
  unidade como "espera" dava falso-positivo em toda atividade com
  predecessora, mesmo com ritmos compatíveis — bug pego e corrigido
  antes de escrever os testes formais. `balancear_ritmos_lob` reporta
  as duas direções de correção (reduzir equipe da sucessora OU acelerar
  a predecessora) — a 1ª pode ser `None` quando nem 1 equipe (mínimo)
  resolve, caso em que só a 2ª é viável.
- Ainda não testado: `gerar_gantt_base64` dentro de uma chamada real
  de tool MCP via protocolo (só testei a função Python direto). Rodar
  `mcp.run()` local e testar com um cliente MCP antes do deploy.
- Autenticação: mesma decisão dos outros MCPs — deixado para depois.
