# Fase 1 — auditoria e plano antes da implementação

**Implementação concluída localmente; avanço depende do CI do HEAD publicado.** Resultado final local: **1.005 aprovados, zero falhas, oito ignorados**, em **50,33 segundos**. Seleção focada: **47 aprovados**. São seleções sobrepostas; não somar. O resultado da Fase 0 em `60033fd` foi conferido antes de criar esta branch.

Base: `60033fdbf7ee1636c9ee4bf362a910f01de86f03`, PR #154, CI completo [39100456150](https://github.com/Yamatosemj/aurenOFC/actions/runs/39100456150) aprovado. Branch: `desenvolvimento/fase-1-tarefas-persistentes`, sem merge.

## O que já existe

`TaskManager` é a fonte operacional de estados, objetivo, chat e passos. O Harness aceita injetar esse manager e já usa begin_step antes do executor e finish_step depois. `PlanBuilder` produz ExecutionPlan/PlanStep. `TaskTraceStore` é observacional; memória guarda conversas/estratégias; a fila executa callbacks auxiliares em memória. Não criar outro executor ou outro gerenciador de estados.

## Mudança planejada

Acrescentar armazenamento SQLite opcional ao TaskManager, preservando o comportamento padrão em memória. Guardar o mesmo registro operacional, o plano existente e histórico de alterações em transações. A persistência deve confirmar begin_step antes do efeito. Falha de escrita restaura o estado anterior em memória e propaga erro; não pode fingir checkpoint gravado.

Um arquivo de dados terá um único manager escritor por vez, com trava de sistema operacional liberada inclusive após morte do processo. Ao reabrir, tarefa antes ativa passa a interrompida; nunca aparece como executando sem processo. Pausa e retomada de checkpoint não executam ferramentas. Etapa sem resultado confirmado exige revisão e impede retomada/conclusão automática. Estados terminais continuam imutáveis. Nenhuma permissão ou aprovação será serializada.

O Harness continua dono da execução. Nesta fase, a API persistente será utilizável por injeção de TaskManager; não abrir banco real nem alterar o armazenamento padrão de usuários durante os testes. O planejamento executável e a ligação de retomada ao ciclo pertencem à Fase 2; a interface ao usuário pertence à Fase 4. Não apresentar a persistência de checkpoint como execução retomada automaticamente.

## Critérios e testes

- Mesmo objetivo/plano/passos recuperados em novo processo, inclusive depois de término abrupto.
- Retomar entre passos preserva os resultados já registrados; um passo sem resultado fica incerto e não se repete.
- Escrita recusada não permite iniciar novo efeito nem altera o estado confirmado.
- Segundo escritor é recusado; morte do primeiro libera a trava.
- Banco corrompido ou de versão futura é recusado, sem iniciar histórico vazio silenciosamente.
- Histórico por chat e estados terminais permanecem consistentes; arquivo arquivado não é perdido pela poda da memória.
- Uso com Harness/Dispatcher/PermissionManager reais e efeitos fictícios: reinício não dispensa confirmação da etapa seguinte.
- Suíte completa, CI nos dois sistemas e documentação antes da próxima fase. Sem API paga ou Live sensível.

## O que foi entregue e comprovado

O mesmo TaskManager agora aceita `db_path` opcional. Não há outro gerenciador de tarefas, executor, planejador ou nova ferramenta exposta ao modelo. O padrão do produto continua em memória até a ligação das fases seguintes. O banco operacional é separado da memória de conversas e do trace porque precisa registrar o estado que pode ser retomado, não apenas observações.

São guardados objetivo, chat, ExecutionPlan existente, passos, estados e eventos. Cada mudança e seu evento são gravados na mesma transação. Se a escrita falha, a alteração em memória é desfeita e o erro aparece ao chamador. A integração com o Harness comprovou que falhar em begin_step impede chegar ao Dispatcher. Uma falha depois do efeito, antes de gravar o resultado, preserva o passo como incerto.

Foi usado um subprocesso real que gravou um efeito fictício em arquivo temporário e terminou abruptamente com `os._exit`. Outro processo recuperou o mesmo objetivo e os mesmos passos. Quando o resultado tinha sido gravado, a seleção do checkpoint pôde ser retomada; quando faltava, a retomada e uma tentativa de inventar o resultado foram recusadas. O arquivo fictício permaneceu com um único efeito. **Selecionar o checkpoint não executa a continuação da tarefa**: essa ligação pertence à Fase 2.

Outras verificações reais de armazenamento: segundo escritor no mesmo processo e em outro processo recusado; trava liberada após morte do dono; aliases por hard link recusados; transação SQL abortada sem gravar estado parcial; arquivo vazio, banco alheio, corrompido ou com versão futura recusados sem iniciar histórico vazio; resultado ou plano com tipos inválidos recusados. A poda da memória não apaga o arquivo de objetivos anteriores; a listagem paginada recupera os arquivados por chat e não mistura conversas.

O Harness persiste o plano do PlanBuilder quando recebe um manager durável e fecha o armazenamento no shutdown. Um checkpoint já pausado ou interrompido não vira cancelamento só porque o canal fechou. Tarefa ainda ativa mantém o cancelamento cooperativo anterior; um pedido de cancelamento persistido não é apagado para permitir retomada. Estado terminal continua imutável. Uma tarefa retomada não pode substituir outra tarefa em execução.

O atalho legado executava antes de registrar o passo. Para cumprir a garantia de gravar antes de agir, **objetivos em modo persistente usam o ciclo normal**, com revisão de intenção, Dispatcher, contratos e permissões. O modo padrão em memória mantém os atalhos. Essa escolha pode acrescentar chamadas ao modelo quando o modo durável for usado; nenhum teste pago foi executado. Não foi criada uma rota paralela de execução.

A confirmação positiva nos testes é exclusivamente simulada, com Popen ou efeitos fictícios. O controle de retomada usa PermissionManager e Dispatcher reais e uma negativa nova para a etapa seguinte; nenhum dado persistido concede aprovação. O arquivo de tarefas não contém estado do PermissionManager.

## API e limites

- `TaskManager(db_path=...)`: persistência explícita em arquivo novo ou reconhecido; sem `db_path`, mantém o comportamento em memória.
- `create(..., plan=...)`, estados e passos existentes: preservam o ciclo operacional.
- `pause()` atua entre passos; `resume_checkpoint(task_id)` apenas seleciona e muda o estado de um checkpoint seguro. Efeito incerto, falha anterior ou cancelamento pendente impedem a retomada automática.
- `get_snapshot`, `list_snapshots(chat_id, limit=..., offset=...)` e `execution_history(task_id, after_sequence=..., limit=...)`: consulta de estado e histórico; não executam ações.
- `close()` libera banco e trava; o shutdown do Harness também o faz. A trava é do arquivo, não depende de confiar em um PID antigo.

O plano salvo ainda é a estimativa heurística existente, não uma sequência autorizada de ações. A Fase 2 deve auditar o planejamento, preservar os dados exatos da ordem, reconstruir verificações pendentes e respeitar orçamento acumulado antes de ligar execução à retomada. Não usar o checkpoint para repetir ferramentas antigas, recuperar PIDs ou restaurar confirmações.

Ainda não há interface de lista/retomada (Fase 4), rotina proativa (Fase 3), execução automática depois de abrir o aplicativo ou migração de dados reais. A retomada depois de falhas é conservadora e requer verificação nova; não há reparo automático de banco danificado. O arquivo guarda texto de objetivos e resultados, sem criptografia ou apagamento automático por prazo nesta fase. A memória de conversas e os bancos existentes não foram alterados. Não foi comprovada resistência a toda alteração hostil do sistema de arquivos, desempenho com histórico muito grande ou retomada do modelo/API reais.

## Evidências e testes anteriores à correção

Os dez testes iniciais falharam antes de existir persistência. As verificações adicionais reproduziram quatro problemas de retomada/concorrência, dois de formato do banco, um de listagem arquivada, dois das fronteiras do Harness e quatro de tipos de checkpoint antes dos ajustes respectivos. Houve também duas falhas de compatibilidade em fixtures antigas de shutdown, corrigidas no código sem relaxar os testes. Todas as execuções preservadas estão em [fase1/RESULTADOS_FASE_1.json](fase1/RESULTADOS_FASE_1.json), com contagens, caminhos das cópias e hashes do código utilizado.

Os testes usam Windows/Python 3.13.15, SQLite e subprocessos reais, mas somente perfil, arquivos e dados fictícios. As oito exclusões da suíte completa são testes de links simbólicos não permitidos no ambiente local. Rede/modelo, dispositivos e programas pessoais não foram usados. O CI no HEAD exato será registrado na PR da fase; nenhum merge à main é autorizado por esses resultados.

## Resultado do CI: fase bloqueada

O CI do código `6f220aab9bf6a0a5aee4488daa0cd6e170c1f144` reprovou no Windows: 1.012 aprovados e uma falha na garantia de término dos processos descendentes do supervisor. Linux: 972 aprovados e 41 ignorados. A recorrência é um risco de segurança; a sequência foi interrompida, sem iniciar a Fase 2. Detalhes e condições de retomada em [BLOQUEIO_CI.md](fase1/BLOQUEIO_CI.md). A entrega está em rascunho na [PR #155](https://github.com/Yamatosemj/aurenOFC/pull/155).

O proprietário autorizou resolver o bloqueio e continuar. A correção adicional e seus limites estão em [CORRECAO_SUPERVISOR.md](fase1/CORRECAO_SUPERVISOR.md); o resultado reprovado permanece preservado. O avanço exige a aprovação do CI final.
