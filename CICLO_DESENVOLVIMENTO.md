# Ciclo sequencial de desenvolvimento do Auren

## Estado para retomada — 18/10/2026

**Fases 0 e 1 validadas; Fase 2 implementada, aguardando suíte completa e CI final. Fases 3 a 5 não iniciadas.** Nenhuma PR foi mesclada. A Fase 1, incluindo a correção adicional do supervisor, passou no CI `39103014489`, SHA `3e93696e66a003983c7f9061cf741cfff0c60984`: Windows 1.022 aprovados; Linux 978 aprovados/44 ignorados.

- Branch atual: `desenvolvimento/fase-2-planejamento-recuperacao`, derivada desse SHA da PR #155. A PR da Fase 2 usa a branch da Fase 1 como base.
- Relatório: [FASE_2.md](docs/desenvolvimento/FASE_2.md). Evidências preservam as falhas iniciais, a regressão da fixture parcial e a falha HTTP local com suas correções.
- O mesmo ciclo executa o objetivo retomado. Checkpoint seguro preserva orçamento e restrições; passos incertos, falhas anteriores, guards em recuperação e fechamentos não são retomados cegamente. Não há restauração de autorização, coordenada, PID ou imagem.
- A verificação de conclusão exige evidências de todas as etapas; uma pendência pode gerar uma recuperação limitada. O julgamento semântico real ainda não foi validado com API.
- Sem API paga, Live sensível, dados pessoais, alteração de main ou runner pessoal. `desktop/` permanece intocada.

## Como retomar

1. Conferir main, branches, PRs e CI no SHA atual; não presumir que resultados de versões anteriores valham para o HEAD.
2. Ler FASE_2.md e RESULTADOS_FASE_2.json. Só avançar com suíte completa e CI Windows/Linux aprovados no código final.
3. Para a Fase 3, auditar a fila auxiliar e os agendamentos existentes. Implementar apenas rotinas explicitamente cadastradas e limites/revogação, com permissão negada por padrão e o mesmo Dispatcher. Sugestões não executam efeitos. Não criar aprovação automática ou tratar texto de arquivo/site como autorização.
4. Fase 4 liga o acompanhamento à interface existente; Fase 5 integra e verifica limites. Não ativar execução de rotinas ao iniciar o aplicativo sem autorização cadastrada.

Não foi definido orçamento para API paga neste ciclo. Testes pagos e ações sensíveis continuam pendentes de autorização e orçamento explícitos. Autorizações de investigações anteriores não constituem orçamento para estas fases.

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
