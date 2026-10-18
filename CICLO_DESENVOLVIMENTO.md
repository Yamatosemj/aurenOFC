# Ciclo sequencial de desenvolvimento do Auren

## Estado para retomada — 18/10/2026

**Fase 0 concluída para desenvolvimento em branch; Fases 1 a 5 ainda não iniciadas.** A revisão das alterações da base e seus contratos foi concluída após reconciliar #152/#153. O bloqueio F0-SEG-001 passou nos testes. Escopo, evidências e limites em [REVISAO_FINAL.md](docs/desenvolvimento/fase0/REVISAO_FINAL.md). Isso não autoriza merge nem comprova todas as funcionalidades em uso real.

- Branch: `desenvolvimento/fase-0-base-auditoria`, criada do HEAD `7df474bb2f6a315ffede684c712999addddb5873` da #153.
- Base da PR de revisão: `correcoes-auditoria`, para mostrar somente a revisão, sem repetir os arquivos da #153. Essa base é provisória e não está aprovada para a Fase 1.
- Evidência e análise: [revisão da Fase 0](docs/desenvolvimento/fase0/REVISAO_BASE.md), [comparação executada](docs/desenvolvimento/fase0/RESULTADOS_COMPARACAO.json) e [testes de segurança](tests/test_phase0_executable_confirmation.py).
- Suíte completa após a reconciliação: **974 aprovados, zero falhas, oito ignorados**, em **49,79 segundos**. Os testes de segurança permaneceram na coleta normal e agora passam. A revisão integral restante continua como critério de avanço pendente.
- Não houve merge, alteração de main, chamada paga, acesso a dados pessoais ou execução de programas reais. A pasta preexistente `desktop/` não foi examinada nem alterada.
- A revisão inicialmente interrompida foi retomada e encerrada no escopo documentado; a base de código reconciliada passou no CI completo em Linux e Windows hospedados.

## Como retomar

1. Conferir novamente main, HEADs, estado e CI das PRs; os hashes abaixo são referências da revisão, não valores permanentes.
2. Conferir a reconciliação na PR #154: a identificação de caminhos é compartilhada entre permissão e executor; mantém confirmação, retorno estruturado e uma única implementação de abertura. A #152 não deve ser mesclada por cima dessa implementação sem nova revisão.
3. Completar a revisão restante da #153 e conferir a evidência da suíte no HEAD reconciliado. A reconciliação e seus testes não substituem essa revisão.
4. Registrar os resultados e a base reconciliada em PR, sem mesclar automaticamente à main. Só então avaliar a entrada na Fase 1.

Não foi definido orçamento para API paga neste ciclo. Chamadas pagas e ações sensíveis ficam pendentes de autorização e orçamento explícitos. Autorizações Live de investigações anteriores não são orçamento para estas fases.

## Critérios de avanço propostos

Cada fase deverá primeiro auditar seus componentes e contratos completos, registrar o plano e trabalhar em branch própria. As fases seguintes ficam empilhadas sobre uma base validada da fase anterior, sem integração automática. Estes são critérios de trabalho; não são funcionalidades já entregues.

| Fase | Reaproveitamento a examinar | Evidência mínima para avançar |
| --- | --- | --- |
| 0 — base | #153, #152, Dispatcher, PermissionManager e abertura de aplicativos | Sobreposição reconciliada; nenhuma proteção perdida; testes do achado e regressões aprovados; revisão restante concluída; base e limites registrados |
| 1 — persistência | TaskManager, TaskSnapshot, TaskStep, memória e trace existentes | Criar objetivo e etapas, encerrar o processo e recuperá-los em outro processo com mesmo histórico; testar falha de gravação, interrupção durante etapa e concorrência; uma etapa de efeito incerto não pode ser repetida cegamente; retomada deve revalidar permissões |
| 2 — planejamento | PlanBuilder, Harness e guards de resultado/recuperação | Objetivo com múltiplas etapas executado e verificado; falha injetada gera recuperação limitada; alternativa fora do escopo é recusada; repetição e orçamento continuam limitados; não declarar sucesso com etapa pendente |
| 3 — proatividade | Fila existente, permissões e mecanismos de agendamento que a auditoria confirmar | Rotina autorizada persiste; relógio controlado comprova disparo único, revogação e limites; conteúdo externo não cria autorização; sugestões não executam efeitos; ação não permitida exige confirmação ou é recusada |
| 4 — interface | AurenUiWorker, canal de confirmação, Tkinter e Chrome existentes | Progresso corresponde ao estado persistido; pausa/cancelamento/retomada testados durante execução e reinício; confirmação expirada ou de sessão antiga é negada; nenhuma rota de execução paralela |
| 5 — integração | Suíte existente, fixtures seguras e supervisor Live | Casos integrados de tarefa longa, interrupção antes/depois de efeito, recuperação e negação de permissão; resultados verificáveis e artefatos por versão; Live somente no escopo autorizado e orçamento aprovado |

## Componentes já identificados

O `TaskManager` já gerencia estados, passos, resultados e cancelamento, mas seu armazenamento operacional é em memória. O `TaskTraceStore` persiste observações, não implementa retomada. A memória SQLite guarda conversas e estratégias, com outra responsabilidade. `PlanBuilder` já produz um plano heurístico local; não deve ser substituído por outro planejador sem auditar sua integração. A fila `AgentTaskQueue` usa callbacks e threads em memória para trabalho auxiliar. O `AurenUiWorker` já serializa mensagens e solicita confirmações. Esse inventário inicial orienta a auditoria de cada fase e não equivale a aprovar um desenho de implementação.
