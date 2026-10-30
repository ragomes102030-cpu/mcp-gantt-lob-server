# Arquimedes — Auditoria técnica dos motores MCP (30/10/2026)

**Escopo:** três repositórios oficiais; análise de código em `master` / `main`
e alterações propostas em `audit/engineering-benchmark-p2-20261030`.
Sem acesso aos bancos reais ou alteração da Plataforma Obras.
**Status:** correções P2 em revisão; NÃO declarar prontidão profissional
irrestrita nem deploy produtivo até CI crítico verde no SHA aprovado.

## Inventário: ferramentas registradas no código

| Motor | Privadas/autenticadas no código | Públicas sem persistência | SDK |
|---|---:|---:|---|
| EAP | 24 | 2 | `mcp==2.3.0` |
| Cronograma | 15 | 2 | `mcp==2.3.0` |
| Gantt/LOB | 7 | 4 | `fastmcp==4.0.3` |
| **Total de registros** | **46** | **8** | MCP HTTP stateless |

**Descoberta real:** o workflow `arquimedes-integrated-pipeline.yml`
executou `list_tools` nas três URLs públicas e comparou os 8 nomes
antes de calcular EAP/CPM/LOB. **Privadas:** lista extraída do código;
não foram enumeradas ou executadas com credenciais nesta auditoria.

### EAP — 24 ferramentas privadas
- **Criação:** `criar_eap_node`, `criar_projeto`, `registrar_retrabalho`, `criar_item_escopo`.
- **Atualização:** `atualizar_eap_node`, `move_eap_node`, `atualizar_projeto`, `definir_criterio`, `vincular_escopo_eap`.
- **Exclusão:** `deletar_eap_node`, `deletar_projeto`, `desvincular_escopo_eap`.
- **Leitura:** `get_eap_node`, `get_eap_tree`, `listar_por_tipo_frente`, `buscar_eap_node`, `listar_projetos`, `resumo_quantitativos`, `listar_templates`, `listar_escopo`.
- **Auditoria:** `validar_estrutura`, `pacotes_sem_dono`, `validar_regra_100_porcento`, `avaliar_evidencia_eap`.
- **Públicas (auditoria):** `validar_estrutura_eap`, `avaliar_evidencia_eap`.

### Cronograma — 15 ferramentas privadas
- **Criação:** `criar_atividade`, `criar_dependencia`, `salvar_baseline`.
- **Atualização:** `atualizar_atividade`; `calcular_caminho_critico` também **escreve resultados**.
- **Exclusão:** `deletar_atividade`, `deletar_dependencia`.
- **Leitura:** `listar_atividades`, `listar_dependencias`, `listar_baselines`.
- **Auditoria:** `validar_dependencias`, `comparar_baseline`.
- **Cálculo:** `calcular_caminho_critico`, `curva_s`, `calcular_duracao_com_evidencia`, `calcular_cpm_com_evidencia`.
- **Públicas (cálculo):** `calcular_duracao_com_evidencia`, `calcular_cpm_com_evidencia`.

### Gantt/LOB — 7 ferramentas privadas
- **Exportação/registro:** `gerar_gantt` (**registra exportação em DB**, não é stateless).
- **Leitura:** `listar_exports`, `listar_temas`.
- **Cálculo:** `calcular_linha_balanco`, `balancear_ritmos_lob`, `dimensionar_equipes_lob`.
- **Auditoria:** `validar_lob_evidencia`.
- **Públicas (sem log/escrita):** `calcular_linha_balanco`, `balancear_ritmos_lob`, `dimensionar_equipes_lob`, `listar_temas`.

## Diagnóstico e decisões

| Prioridade | Evidência | Correção/limitação |
|---|---|---|
| **Alta** | `models/cpm.py`: folga livre anterior assumia TI para II/TT/IT | Margens dependentes do tipo e do lag; benchmark de rede enumerada independente |
| **Alta** | `models/cpm.py`: arestas órfãs ignoradas no sort e depois utilizadas | Rejeição antes de gravar resultados |
| **Alta** | `models/escopo.py`: comparação de `scope_id` com ele próprio era inefetiva, `INSERT OR REPLACE` podia mudar vínculo principal silenciosamente | Rejeitar transferência não autorizada e preservar idempotência |
| **Alta** | `models/atividades.py`: PERT sem verificação de ordem/finitude, duração e progresso inadequados | Bloquear resultados inconsistentes sem criar atividades |
| **Alta** | `models/dependencias.py`: lag não finito podia entrar na base | Bloquear lag NaN/inf e limites extremos |
| **Alta** | `models/gantt.py`: períodos invertidos/progresso inválido e rótulos XLSX interpretáveis como fórmula | Validar e escapar etiquetas com possível fórmula |
| **Média** | `models/lob.py`: `date + timedelta` perde frações de dia nas datas civis | Adicionar `data_hora_inicio/fim`, mantendo campos legados |
| **Média** | Export XLSX não levava `activity_id/eap_uid/location_id/baseline_id` | Campos opcionais no input e aba aditiva `Rastreabilidade` |
| **Aberto** | Cronograma privado exige `EAP_SERVER_URL` para criar atividade | Comportamento fail-closed preservado; propor validação/snapshot no orquestrador sem remover exigências de escrita |
| **Aberto** | Baseline: snapshot é preservado, mas aprovação/imobilidade formal e governança de uma única ativa não demonstradas por schema/DB | Requer desenho de migração revisada e autorização de DB |
| **Aberto** | LOB modela sequência linear e divisibilidade ideal `tempo_unitario / equipes`, sem grafo de múltiplas frentes ou calendário de trabalho | Piloto de repetitivos, não representa toda a obra |
| **Aberto** | `gerar_gantt` é ferramenta privada autenticada; não há export XLSX público | Teste XLSX local, nunca exposição anônima de export persistente |
| **Aberto** | Integração entre motores é envelope/adaptador, não referencial compartilhado transacional | Sem bancos unificados; ativação em modo sombra exige trabalho posterior |
| **Aberto** | Falta operação monitorada com SLO, tráfego real auditado e observabilidade completa | Não atribuir maturidade 5 |

## Benchmark matemático e integração
- `tests/test_arquimedes_engineering_benchmark.py` em cada motor contém entradas fictícias, esperados explícitos e tolerâncias.
- CPM: enumerador independente de todos os cronogramas viáveis de redes pequenas; relações TI/II/TT/IT e lags; passagem ES/EF/LS/LF, folga total/livre e crítico.
- EAP: escopo de referência 50% depois 100%, UID estável e posse principal, isolamento de projetos.
- LOB: 3 e 4 pavimentos, ritmos diferentes, continuidade da equipe, 0,5 dia com horário preciso; XLSX reaberto via `openpyxl`.
- `arquimedes-integrated-pipeline.yml` consulta as três tools públicas em obra fictícia: 3 nós EAP, CPM de 5 dias, LOB de 8 dias, 8 ferramentas descobertas. Simula MCP indisponível e exige `BLOQUEADO` sem cálculo fictício.
- `arquimedes-engineering-benchmark.yml` salva JUnit, relatório JSON, commit, data, resultado por caso, propriedades esperado/obtido/diferença/tolerância quando aplicáveis.
- **Não testado com credenciais privadas:** XLSX via MCP remoto autenticado e mudanças no banco real; não declarar que ocorreu.

## Contrato/skills/Plataforma Obras
- Contrato em `docs/CONTRATO_INTEROPERABILIDADE_V1.md` nos três repos.
- Skills técnicas em `docs/skills/` dos motores correspondentes.
- Plataforma Obras permanecerá desconectada. Reativação futura em **shadow mode**,
com timeout, fallback interno, circuit breaker, rastreabilidade de SHA e veto a escritas sem autorização.

## Critério de liberação
Só liberar commits com regressão completa, benchmark independente e teste de
interoperabilidade verde. Publicar na Vercel a partir da branch principal e
verificar SHA, tools e endpoint privado antes de declarar sucesso.

## Maturidade conservadora
- **EAP: nível 3** — integridade estrutural e evidência de escopo, mas revisão humana semântica, EAP persistente não verificada remotamente.
- **Cronograma: nível 3** — cálculo CPM referenciado, mas dependência para validação EAP privada e baseline/calendário ainda incompletos.
- **Gantt/LOB: nível 3** — LOB repetitiva e XLSX ensaiados; redes completas por local, integração autenticada e operação monitorada não cobertas.
- **Nível 4 e 5 não atestados globalmente**; faltam integração completa autorizada, observabilidade e aprovação operacional.
