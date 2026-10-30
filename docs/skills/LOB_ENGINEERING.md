# Skill — Linha de Balanço (procedimento, não algoritmo)

**Quando usar:** sequenciamento de serviços repetitivos por localização ordenada, ritmo/equipes/interferência.

**Entradas obrigatórias:** unidades/localizações únicas e ordenadas, IDs estáveis dos serviços, tempo unitário, número de equipes, pulmão mínimo, data zero e fonte das produtividades.

**Tools públicas:** `calcular_linha_balanco`, `dimensionar_equipes_lob`, `balancear_ritmos_lob`. **Privadas:** `validar_lob_evidencia` e ferramentas de Gantt, apenas com autorização.

**Validações:** durações positivas finitas, equipes inteiras, local sem duplicidade, precedência entre serviços na mesma unidade, equipe sem simultaneidade em duas unidades, ritmos compatíveis, esperas e durações fracionárias com horários exatos. O motor atual assume uma única sequência linear de serviços e o modelo simplificado de divisão do tempo unitário pelo número de equipes.

**Revisão humana:** frentes múltiplas, restrições reais de equipes, ciclos/pavimentos, atividades não repetitivas, segurança operacional, interferências no espaço e sequência construtiva. Não prometer representação profissional de toda a obra em um único gráfico enquanto faltar suporte explícito a redes de locais e calendários.

**Erros bloqueantes:** locais duplicados, tempo não finito, equipes inválidas, calendário não definido quando datas úteis obrigatórias, dependências que o modelo simplificado não consegue representar.

**Saída:** escadinhas por serviço/unidade, ritmo/equipes, início/fim exatos em dias/horas, tempo de espera, premissa de calendário, origem e pontos para revisão.
