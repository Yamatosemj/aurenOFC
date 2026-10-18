# Ciclo sequencial de desenvolvimento do Auren

## Estado para retomada — 18/10/2026

**Fases 0 a 3 validadas; Fase 4 implementada, aguardando CI final. Fase 5 não iniciada.** Base: PR #157, `2313f1d`, CI `39129372163` aprovado (1.055 Windows; 1.011 Linux/44 ignorados). Nenhum merge.

- Branch: `desenvolvimento/fase-4-interface-tarefas`, empilhada na Fase 3.
- Relatório: [FASE_4.md](docs/desenvolvimento/FASE_4.md); evidências em `docs/desenvolvimento/fase4/RESULTADOS_FASE_4.json`.
- Suíte local: 1.055 aprovados, zero falhas, oito ignorados. Painel Chrome e tabela Tk usam o worker/Harness existentes; Chrome cadastra e autoriza rotinas em passos separados.
- Worker padrão passa banco operacional explícito e encerra pelo Harness.shutdown. Não abre banco até pedido de carregar tarefas ou mensagem. Não se retomam objetivos ou aprovam rascunhos automaticamente.
- Corrida de Desligar antes da criação do objetivo reproduzida e corrigida; controles/autorizações e execução obedecem à geração da sessão.
- Nenhuma API paga, dados pessoais, Live sensível, mudança de main ou runner. `desktop/` intocada.

## Como retomar

1. Conferir main, HEADs, PRs e CI da Fase 4 no SHA final. Só avançar com suíte completa e ambos os jobs aprovados.
2. Fase 5: bateria integrada com dados fictícios, tarefa longa, pausas/reinício, reserva/efeito incerto, falhas de armazenamento, negação de permissões, gerações antigas e revogação. Reutilizar banco e ciclo existentes.
3. Quando possível, validar a interface real em browser isolado com perfil temporário, rede externa bloqueada e provider/efeitos fictícios. Não usar perfil/browser pessoal nem chamar a API real.
4. Distinguir teste integrado/componentes reais de Live completo do Auren. Modelo/API reais e ações sensíveis continuam sem orçamento autorizado; documentar o que falta e interromper nesse limite, sem inventar aprovação.

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
