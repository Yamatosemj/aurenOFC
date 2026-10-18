# Ciclo sequencial de desenvolvimento do Auren

## Estado para retomada — 18/10/2026

**Fases 0 a 2 validadas; Fase 3 implementada, aguardando CI final. Fases 4 e 5 não iniciadas.** Base: PR #156, `a2b0961`, CI `39128640968` aprovado (1.044 Windows; 1.000 Linux/44 ignorados). Nenhum merge.

- Branch: `desenvolvimento/fase-3-proatividade-controlada`, empilhada na Fase 2.
- Relatório: [FASE_3.md](docs/desenvolvimento/FASE_3.md); evidências em `docs/desenvolvimento/fase3/RESULTADOS_FASE_3.json`.
- Suíte local: 1.047 aprovados, zero falhas, oito ignorados. Rotinas usam o mesmo TaskManager/SQLite; aprovação de agenda não substitui PermissionManager.
- A agenda só dispara por tick explícito nesta fase. Sugestão não chama modelo ou ferramenta. Rotina executável exige escopo exato e orçamento, e fica interrompida diante de resultado incerto. Não é retomada sem escopo.
- Sem API paga, dados pessoais, Live sensível, alteração de main ou runner. Pasta `desktop/` intocada.

## Como retomar

1. Conferir main, HEADs, PRs e CI no SHA final da Fase 3. Só avançar com suíte completa e ambos os jobs aprovados.
2. Auditar worker/Chrome/Tk existentes antes da Fase 4. Integrar progresso/pausa/cancelamento/retomada e confirmação pelo mesmo worker/Harness, sem outro executor.
3. Mostrar as condições de uma rotina antes de autorizar; cadastro é rascunho e não pode ser aprovado por texto do modelo. Conferir geração/sessão antes de comandos e confirmações. Não ativar rascunhos ao abrir a interface. Rodar agenda somente para chat ativo e autorizado.
4. Na Fase 5, testar integração, falhas e reinício com dados fictícios. API paga e ações sensíveis continuam sem orçamento aprovado; não executar nem declarar aprovados esses cenários.

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
