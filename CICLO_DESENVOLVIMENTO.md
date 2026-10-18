# Ciclo sequencial de desenvolvimento do Auren

## Estado para retomada — 18/10/2026

**Fases 0–4 em PRs; correções F5-LIVE-001/002 implementadas em branch própria. Suíte final local aprovada; contrato final do revisor ainda requer Live.** [correções e evidências Live](docs/desenvolvimento/fase5/CORRECOES_LIVE.md). Sem merge.

- Branch: `desenvolvimento/fase-5-validacao-integrada`, empilhada na Fase 4.
- Relatório simples: [RELATORIO_DESENVOLVIMENTO.md](RELATORIO_DESENVOLVIMENTO.md). Detalhes: [FASE_5.md](docs/desenvolvimento/FASE_5.md).
- Suíte local: 1.057 aprovados, zero falhas, oito ignorados, 62,50 s. Integração real entre processos: 16 passos, pausa após oito, saída abrupta e retomada sem repetir observações; outra queda após efeito recusa retomada.
- Interface real isolada: oito controles aprovados, Chromium temporário com sandbox e origem local, Tk com janela retirada. Modelo fictício, quatro chamadas fictícias, zero API, zero efeitos pessoais e nenhuma confirmação positiva automatizada no browser. Supervisor terminou com código zero; banco reaberto com pausa intacta.
- Tentativas anteriores preservadas: recusa do Chrome instalado e erro de seletor no script de validação. Não foram alterados perfil/política pessoal, instalação do runner ou workflow para contornar erros.
- Nenhum dado pessoal, hardware/voz, aplicativo/perfil pessoal ou alteração de main. `desktop/` permanece intocada.

## Como retomar

1. Conferir a branch `desenvolvimento/fase-5-correcoes-live`, sua PR e CI do HEAD final; não integrar à main automaticamente.
2. As correções e regressões locais estão concluídas. Conferir o relatório CORRECOES_LIVE.md antes de atribuir aprovação Live à versão final.
3. Preservar o registro global de gastos e tentativas: orçamento autorizado US$ 2, custo estimado US$ 0,01942, reserva preventiva US$ 1,944 e teto conservador de 24 chamadas atingido. Não zerar contagem ou aumentar teto automaticamente.
4. Antes de aprovar a Fase 5 integral, validar com API o novo campo answer_status (resposta correta/incorreta e evidência ausente), sem dispensar referências ou observação posterior aos efeitos.
5. Manter PRs em rascunho, main intacta e limites de Live não cobertos explícitos.

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
