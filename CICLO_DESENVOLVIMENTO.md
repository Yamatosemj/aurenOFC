# Ciclo sequencial de desenvolvimento do Auren

## Estado para retomada — 18/10/2026

**Fase 0 concluída; Fase 1 implementada e testada localmente, aguardando CI antes da Fase 2. Fases 2 a 5 não iniciadas.** O HEAD `60033fd` da Fase 0 passou no [CI completo final](https://github.com/Yamatosemj/aurenOFC/actions/runs/39100456150): 986 aprovados no Windows e 945 aprovados/41 ignorados no Linux. A Fase 1 usa essa base e estende o TaskManager existente; não cria executor paralelo nem retoma ações automaticamente. Relatório e limites em [FASE_1.md](docs/desenvolvimento/FASE_1.md).

- Branch atual: `desenvolvimento/fase-1-tarefas-persistentes`, derivada de `60033fdbf7ee1636c9ee4bf362a910f01de86f03` da PR #154. A PR de Fase 1 deve usar `desenvolvimento/fase-0-base-auditoria` como base, sem merge à main.
- Fase 0 e falhas anteriores preservadas em [REVISAO_FINAL.md](docs/desenvolvimento/fase0/REVISAO_FINAL.md), [SUPERVISOR_WINDOWS.md](docs/desenvolvimento/fase0/SUPERVISOR_WINDOWS.md) e seus JSONs. O run `39099859051` falhou; somente a conferência posterior aprovada permitiu avançar.
- Fase 1: SQLite opcional, eventos transacionais, plano persistido, estados PAUSED/INTERRUPTED, trava de escritor e retomada conservadora de checkpoint. Sem ligação à interface ou execução continuada automática.
- Suíte completa local atual: **1.005 aprovados, zero falhas, oito ignorados**, em **50,33 segundos**; seleção focada com 47 aprovados. [Evidências da Fase 1](docs/desenvolvimento/fase1/RESULTADOS_FASE_1.json).
- Sem merge, alteração de main, API paga, Live sensível ou dados pessoais. Processos Python e arquivos das fixtures são reais e fictícios; não são programas pessoais. A pasta preexistente `desktop/` não foi examinada nem alterada.

## Como retomar

1. Conferir novamente main, HEADs, estado e CI das PRs; os hashes abaixo são referências da revisão, não valores permanentes.
2. Conferir a reconciliação na PR #154: a identificação de caminhos é compartilhada entre permissão e executor; mantém confirmação, retorno estruturado e uma única implementação de abertura. A #152 não deve ser mesclada por cima dessa implementação sem nova revisão.
3. Conferir o relatório da Fase 1 e o CI do seu HEAD publicado. Só avançar com todos os critérios aprovados; SQLite recuperado não equivale a continuação de execução entregue.
4. Na Fase 2, auditar PlanBuilder e o ciclo existente, especialmente dados exatos, verificação de resultados, orçamento acumulado e estado dos guards após retomada. Implementar a continuação em branch própria derivada da Fase 1, sem segundo executor nem restauração de aprovações.

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
