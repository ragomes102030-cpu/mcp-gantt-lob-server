# Arquimedes P4 — EAP → duração → CPM com calendário → LOB por local

**Implementação:** adaptador stateless importável em
`mcp_gantt_lob/arquimedes_orchestrator.py`, cliente executável
`scripts/clients/arquimedes_orchestrator_smoke.py`. Nenhum dos três
servidores depende obrigatoriamente dos outros.

## Entrada e política de segurança
- `schema_version: "1.0"`, `project_id` opaco, `eap_nodes` com
  `eap_uid` estável independente de `eap_id`.
- `atividades` por pacote EAP folha, com `activity_id`, `eap_uid`,
  `quantidade`, `produtividade`, unidades compatíveis, fonte,
  responsável, critério de aceite e `locais_atividade` opcionais.
- `locais`: lista ordenada de `location_id`; `dependencias`:
  vínculo TI explícito por par atividade/local. Cadeias de equipes
  `equipe_id` são materializadas como vínculos TI de recurso.
- `data_inicio` e `calendario` são obrigatórios. `modo` pode ser
  `uteis` (duração e lag inteiros; dias da semana e feriados explícitos)
  ou `corridos` (frações admitidas).
- Escopo máximo **150 tarefas atividade-local** por execução, limitado
  pela ferramenta CPM pública. Recusamos fragmentação automática, porque
  perderia dependências entre lotes.
- Nenhuma operação tem efeito colateral. O adaptador aceita uma função
  `call(motor, ferramenta, argumentos)` injetada e exige
  `persistido: false` nas respostas. O cliente externo aplica timeout
  por chamada e tempo máximo do fluxo.

## Fluxo verificado
1. Valida localmente UID único, códigos, atividades, locais e vínculos.
2. Chama `validar_estrutura_eap` e `avaliar_evidencia_eap` no MCP EAP.
3. Consulta `calcular_duracao_com_evidencia` para cada serviço, sem
   aceitar duração arbitrária dada pelo agente. **Quantidade é por local.**
4. Expande `activity_id::location_id` em tarefa de cronograma e cria
   vínculos TI explícitos e cadeias sequenciais de equipes.
5. Chama `calcular_cpm_com_calendario` (novo método P4) no Cronograma.
6. Chama `calcular_lob_com_vinculos` no Gantt/LOB.
7. Confere todos os `eap_uid`, IDs, ES, EF, datas de início e fim exclusivo,
   duração total e ausência de tarefas faltantes/duplicadas.
8. Em qualquer divergência ou indisponibilidade, encerra como
   **BLOQUEADO**, sem produzir prazo fabricado.

**Importante:** número de equipes significa divisão ideal de duração
em uma mesma tarefa; não resolve alocação real de recursos. Não há
conversão automática de unidades, sazonalidade, feriados locais presumidos
ou relações II/TT/IT na LOB. Restrições adicionais de início não são
aceitas no adaptador conjunto até que ambos os motores as reproduzam.

## Exemplo fictício
`python scripts/clients/arquimedes_orchestrator_smoke.py`

Cenário conhecido: EAP 3 nós, atividades F01/A01 em P01/P02,
quantitativos/produtividades gerando 2 e 3 dias/unidade, dependências
TI por pavimento, calendário útil seg–sex com feriado explícito
03/11/2026. Referência: CPM 8 dias úteis, LOB 8 dias úteis, 4
tarefas, dois UIDs estáveis e nenhum dado persistido.

`python scripts/clients/arquimedes_orchestrator_smoke.py --simulate-unavailable`
deve sair com código 2 e JSON `status=BLOQUEADO`, não fazer fallback
silencioso. `--json entrada.json` permite avaliar entrada própria
autorizada; nenhum projeto é consultado automaticamente.

## Liberação
Executar suíte isolada de cada repositório; validar endpoints prévia,
compatibilidade dos nomes antigos; verificar após deploy o cenário real
por cliente MCP, incluindo feriado, comparação CPM/LOB e modo bloqueado.
Não ativar na Plataforma Obras sem teste sombra e autorização separada.
