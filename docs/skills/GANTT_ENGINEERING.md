# Skill — Gantt e exportação XLSX (procedimento, não algoritmo)

**Quando usar:** representar e exportar cronograma previamente calculado, com marcos, caminho crítico, progresso e baseline.

**Entradas obrigatórias:** datas do motor CPM validado, ID de atividade, nome/seção, início, fim previsto, progresso 0–100, status crítico, `baseline_id` se houver, proveniência e calendário.

**Ferramentas:** `listar_temas` pública; `gerar_gantt` e `listar_exports` privadas e autenticadas. XLSX não está disponível anonimamente na rota pública.

**Validações:** início <= fim, porcentagem finita de 0 a 100, marcos explicitamente zero dias, atividade crítica fornecida pelo CPM, sem recálculo oculto de precedências, carga XLSX pelo openpyxl e inspeção das linhas.

**Revisão humana:** relações de execução, marcos, baseline, legenda e datas de fechamento. Verificação normativa não coberta.

**Erros bloqueantes:** datas invertidas, status contraditório, XLSX corrompido, ausência da origem CPM, escrita/exportação não autorizada ou transporte indisponível.

**Saída:** XLSX auditado, hash opcional do artefato, nomes/IDs, status, origem e limitações. Manter o módulo interno como fallback e não aceitar como cálculo oficial de obra sem revisão.
