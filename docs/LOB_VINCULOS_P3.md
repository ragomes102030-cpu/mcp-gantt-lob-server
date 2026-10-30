# Arquimedes P3 — LOB com vínculos explícitos e integração segura

## Arquitetura
**Os três servidores MCP continuam independentes.** EAP valida o escopo,
Cronograma calcula o CPM e o Gantt/LOB recebe um envelope explícito validado
pelo orquestrador (ChatGPT, Claude, Arquimedes ou outro cliente). Não há
chamadas MCP internas entre servidores, dependências de bancos alheios ou
gravações externas nesta ferramenta.

## Ferramenta aditiva pública
`calcular_lob_com_vinculos` recebe:
- `atividades`: [{`activity_id`, `nome`, `eap_uid`?, `duracao_dias`,
  `numero_equipes`?=1, `equipe_id`?, `locais_atividade`?=[todos]}]
- `locais`: IDs ordenados e únicos dos locais/pavimentos
- `dependencias`: [{`predecessora_id`, `predecessora_local`,
  `sucessora_id`, `sucessora_local`, `tipo`?="TI", `lag_dias`?=0}]
- `restricoes_inicio` opcional: [{`activity_id`, `location_id`,
  `inicio_minimo_dia`}]
- `data_inicio` opcional: ISO YYYY-MM-DD
- `calendario` opcional: {`calendar_id`: "CAL-1",
  `modo`: "uteis", `dias_semana`: [0,1,2,3,4],
  `feriados`: ["2026-11-03"]}

Exemplo fictício:
```json
{
  "atividades": [
    {"activity_id":"EST","eap_uid":"uid-estrutura","duracao_dias":2},
    {"activity_id":"ALV","eap_uid":"uid-alvenaria","duracao_dias":3}
  ],
  "locais":["P01","P02"],
  "dependencias":[
    {"predecessora_id":"EST","predecessora_local":"P01","sucessora_id":"ALV","sucessora_local":"P01"},
    {"predecessora_id":"EST","predecessora_local":"P02","sucessora_id":"ALV","sucessora_local":"P02"}
  ],
  "data_inicio":"2026-11-02"
}
```
Resultado esperado: 4 tarefas, prazo de **8 dias corridos**, sem persistência.

## Invariantes
- Toda referência atividade-local precisa existir; ciclos rejeitados antes de retornar.
- As equipes lógicas não podem ocupar duas tarefas simultaneamente.
- A mesma `equipe_id` é sequenciada por atividade e ordem de locais,
  e pode ser compartilhada entre serviços **somente de modo explícito**.
- Entre tarefas de serviços diferentes não se presume vínculo. Devem ser
  fornecidas dependências.
- Permite tarefas restritas a alguns locais, evitando forçar serviço repetitivo
  sobre toda a obra.
- Nesta primeira versão da LOB de rede: apenas **TI (FS)** e lag **não
  negativo**. As quatro precedências continuam no CPM. Não simular as
  demais relações na LOB.
- O número de equipes divide idealmente o tempo unitário **na mesma tarefa**;
  não é um algoritmo de alocação de equipes reais entre pavimentos.
- Calendário `uteis` é discreto e exige **durações, lags e restrições inteiras**.
  Feriados são explícitos; os dias úteis são 0=segunda a 6=domingo.
- As datas de término são **exclusivas**; `data_fim_exclusiva` na sexta
  com uma jornada pode ser a segunda seguinte. Não confundir com data de
  última execução física. Os cálculos em dias corridos aceitam frações de dia.
- Fail-closed em entradas inválidas, IDs órfãos, ciclos, datas malformadas.
  Sem consultas ao banco, sem sobrescrever baseline ou valores oficiais.

## Interoperabilidade e publicação
Ferramentas atuais `calcular_linha_balanco`, `balancear_ritmos_lob`,
`dimensionar_equipes_lob` e `listar_temas` seguem inalteradas.
Clientes MCP precisam atualizar a descoberta de ferramentas para enxergar
a quinta função pública após um deploy. O cadastro do ChatGPT pode requerer
atualização/reconexão; a ferramenta nova não aparece automaticamente em
uma conversa já iniciada.

Não reativar a Plataforma Obras em produção nesta etapa. Antes de usar
resultados oficiais: comparação em modo sombra, revisão de origem/versão,
validação de calendário contratual, e autorização formal de escrita.

## Limites e pendências
Sem restrição de recursos globais ou otimização de equipes, sem tipos
II/TT/IT na LOB, sem relação com preço, quantidade ou produtividade
por unidade. O CPM segue o responsável pela rede lógica macro e pela
criticalidade; LOB de locais não recalcula o CPM.
