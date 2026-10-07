# Auren — Estado oficial do projeto

> **Este arquivo é a fonte de verdade operacional do Auren.**
> Antes de iniciar uma nova tarefa, consulte este arquivo e compare com a branch/PR e o CI do GitHub.
> Não trate roadmap antigo, memória da conversa ou documentos arquivados como estado atual.

Atualizado em: 2026-10-07 (Browser Intelligence — PR #58 em execução)

## Estado agora

- **Base estável (main):** V47
- **Trabalho ativo:** Estabilização e limpeza pós-V47
- **Branch/PR ativa:** `feat/browser-context` / PR #58
- **Head da main:** 709dcf01771849d5711a31ed65ccbc6e02fc33ad
- **Head da PR #58:** 8769e5c2788a86d506172bcad3891b951cf3baed
- **Status da PR #6:** merged
- **Status da PR #9:** merged — item 1 da revisão geral
- **Status da PR #11:** merged — item 3 da revisão geral
- **Status da PR #12:** merged — item 4 da revisão geral
- **Validação da PR #12:** 283 passed, 6 skipped
- **Status da PR #13:** merged — item 5, primeira extração segura do Harness
- **Validação da PR #13:** 283 passed, 6 skipped; focused visual Linux/Windows passaram
- **Status da PR #14:** merged — item 5, segunda extração segura do Harness
- **Validação da PR #14:** 283 passed, 6 skipped; focused visual Linux/Windows passaram
- **Status da PR #15:** merged — item 5, terceira extração segura do Harness
- **Validação da PR #15:** 283 passed, 6 skipped; focused Linux/Windows passaram
- **Status da PR #16:** merged — item 5, quarta extração segura do Harness
- **Validação da PR #16:** 283 passed, 6 skipped; focused Linux/Windows passaram
- **Status da PR #17:** merged — item 5, quinta extração segura do Harness
- **Validação da PR #17:** 283 passed, 6 skipped; focused Linux/Windows passaram
- **Status da PR #18:** merged — item 5, sexta extração segura do Harness
- **Validação da PR #18:** 283 passed, 6 skipped; focused Linux/Windows passaram
- **Status da PR #19:** merged — item 5, sétima extração segura do Harness
- **Validação da PR #19:** 283 passed, 6 skipped; focused Linux/Windows passaram
- **Status da PR #20:** merged — item 5, oitava extração segura do Harness
- **Validação da PR #20:** 283 passed, 6 skipped; focused visual Linux/Windows passaram
- **Status da PR #21:** merged — item 5, nona extração segura do Harness
- **Validação da PR #21:** 283 passed, 6 skipped; focused visual Linux/Windows passaram
- **Status da PR #22:** merged — item 5, décima extração segura do Harness
- **Validação da PR #22:** 283 passed, 6 skipped; focused visual Linux/Windows passaram
- **Status da PR #23:** merged — item 5, décima primeira extração segura do Harness
- **Validação da PR #23:** 288 passed, 6 skipped; focused visual Linux 65 passed, 6 skipped; Windows 71 passed
- **Status da PR #24:** merged — item 5, décima segunda extração segura do Harness
- **Validação da PR #24:** 293 passed, 6 skipped; focused visual Linux 65 passed, 6 skipped; Windows 71 passed
- **Status da PR #25:** merged — item 5, décima terceira extração segura do Harness
- **Validação da PR #25:** 296 passed, 6 skipped; focused visual Linux 65 passed, 6 skipped; Windows 71 passed
- **Status da PR #26:** merged — item 5, décima quarta extração segura do Harness
- **Validação da PR #26:** 300 passed, 6 skipped; focused visual Linux 65 passed, 6 skipped; Windows 71 passed
- **Status da PR #27:** merged — item 5, décima quinta extração segura do Harness
- **Validação da PR #27:** 303 passed, 6 skipped; focused visual Linux 65 passed, 6 skipped; Windows 71 passed
- **Status da PR #28:** merged — item 5, décima sexta extração segura do Harness
- **Validação da PR #28:** 303 passed, 6 skipped; focused visual Linux 65 passed, 6 skipped; Windows 71 passed
- **Status da PR #29:** merged — item 5, décima sétima extração segura do Harness
- **Validação da PR #29:** 314 passed, 6 skipped; focused visual Linux 65 passed, 6 skipped; Windows 71 passed
- **Status da PR #30:** merged — item 5, décima oitava extração segura do Harness
- **Validação da PR #30:** 317 passed, 6 skipped; focused visual Linux 65 passed, 6 skipped; Windows 71 passed
- **Status da PR #31:** merged — item 5, décima nona extração segura do Harness
- **Validação da PR #31:** 321 passed, 6 skipped; focused visual Linux 65 passed, 6 skipped; Windows 71 passed
- **Status da PR #32:** merged — item 5, vigésima extração segura do Harness
- **Validação da PR #32:** 324 passed, 6 skipped; focused visual Linux 65 passed, 6 skipped; Windows 71 passed
- **Status da PR #33:** merged — item 5, vigésima primeira extração segura do Harness
- **Validação da PR #33:** 333 passed, 6 skipped; focused visual Linux 65 passed, 6 skipped; Windows 71 passed
- **Status da PR #34:** merged — item 5, vigésima segunda extração segura do Harness
- **Validação da PR #34:** 336 passed, 6 skipped; focused visual Linux 65 passed, 6 skipped; Windows 71 passed
- **Status da PR #35:** merged — item 5, vigésima terceira extração segura do Harness
- **Validação da PR #35:** 342 passed, 6 skipped; focused visual Linux 65 passed, 6 skipped; Windows 71 passed
- **Status da PR #36:** merged — item 5, vigésima quarta extração segura do Harness
- **Validação da PR #36:** 345 passed, 6 skipped; focused visual Linux 65 passed, 6 skipped; Windows 71 passed
- **Focused visual CI:** Linux passou; Windows passou
- **Auditoria final V47:** concluída antes do merge; nenhum bloqueador funcional ou review pendente identificado.
- **Refactor estrutural PRs #37–#57:** todas merged; allowlist/prompt injection/permissões/exceções/dependências/modelo concluídos, Windows dividido por domínio, Browser dividido por leitura/elementos/navegação, Harness reduzido e bateria live separada do pytest.
- **Validação da rodada final:** PR #57 passou em pytest completo, focused Linux e focused Windows.

A V47 de geometria/coordenadas foi incorporada à main pelo merge commit c0994db89aff396e0dfe43900841e0a766150b73. A main passa a ser a base estável da V47.

## Tarefa atual

**Iniciar Browser Intelligence:**

1. manter o comportamento atual do browser intacto
2. definir o primeiro corte/capacidade de contexto de navegador com escopo pequeno
3. validar abas, página ativa e conteúdo relevante usando as ferramentas existentes
4. não iniciar novas integrações fora do navegador

## Revisão geral concluída

- [x] item 1 — adicionar `runtime/` ao `.gitignore`
- [x] item 2 — separar decisão de permissão do canal de confirmação
- [x] item 3 — decidir por estrutura entre remover ou ligar de verdade
- [x] item 4 — remover ou mover somente código confirmado como morto
- [x] item 5 — extrair arquivos gigantes em PRs pequenos

Situação desta rodada: segurança crítica concluída nas PRs #37–#42; `tools/windows.py` foi reduzido à fachada de 114 linhas após as extrações por domínio; `tools/browser.py` ficou como fachada de 373 linhas com leitura, elementos e navegação separados; `core/harness.py` caiu para 758 linhas após separar runtime e ciclo de execução; `testes_auren_live.py` passou a ser o runner canônico de regressão live, enquanto `testes_auren.py` permanece apenas como fachada de compatibilidade. Todas as PRs desta sequência tiveram CI completo, focused Linux e focused Windows verdes antes do merge.

## Revisão geral em execução

- [x] item 1 — adicionar `runtime/` ao `.gitignore`
- [x] item 2 — separar decisão de permissão do canal de confirmação
- [x] item 3 — decidir por estrutura entre remover ou ligar de verdade
- [x] item 4 — remover ou mover somente código confirmado como morto
- [x] item 5 — extrair arquivos gigantes em PRs pequenos

Situação desta rodada: versão/config/facade alinhados; a árvore atual contém apenas documentação normativa/operacional no pacote principal; o workflow agora também é acionado por push da main; o trace persistente por tarefa foi implementado e incorporado à main; no item 3, os caminhos sem efeito operacional foram removidos e o PlanBuilder foi preservado por uso real no Harness; no item 4, código sem consumidor foi removido, o wake-word foi movido para `experimental/`, e o verificador manual V46 obsoleto foi removido. `CapabilityResolver`/`IntentResolver`/`TaskSpec` e o caminho de áudio experimental permaneceram por terem chamadas reais, ainda que protegidas por flag. No item 5, a PR #13 extraiu a redação/serialização dos logs para `core/harness_logging.py`, preservando a API e os paths de sessão no Harness; a PR #14 extraiu as três heurísticas determinísticas para `core/harness_heuristics.py`, preservando os métodos estáticos no `AurenHarness` por wrappers compatíveis; a PR #15 extraiu a validação determinística de abas múltiplas para `core/harness_multitab.py`, preservando os métodos públicos do `AurenHarness` por wrappers compatíveis; a PR #16 moveu `_ultima_acao_solicitada` para `core/harness_heuristics.py`, preservando o método estático no `AurenHarness`; a PR #17 extraiu `_texto_seguro` e `_argumentos_da_chamada` para `core/harness_serialization.py`, preservando os métodos estáticos no `AurenHarness`; a PR #18 extraiu `_limite_adaptativo` para `core/harness_heuristics.py`, preservando o método estático no `AurenHarness` e removendo o `import re` que ficou sem uso; a PR #19 extraiu a montagem do input visual de `image_path` para `core/vision.py`, preservando no Harness apenas os flags de reobservação e sem alterar a conversão de coordenadas; a PR #20 extraiu a montagem da mensagem de conclusão local para `core/harness_completion.py`, preservando o método estático no `AurenHarness` por wrapper compatível; a PR #21 extraiu a montagem do estado da tarefa para `core/harness_state.py`, preservando o método no `AurenHarness` por wrapper compatível e passando explicitamente o contexto, limites e serializador efetivamente usados; a PR #22 extraiu a montagem do input de cada rodada para `core/harness_round_input.py`, preservando o contrato de retorno, os objetos `function_call`, os `function_call_output`, o caminho visual e o reset dos guards de visão; a PR #23 extraiu a persistência da estratégia em background para `core/harness_strategy.py`, preservando o wrapper do Harness, a captura antecipada do `chat_id`, a prioridade da fila, o cancelamento, o log de enfileiramento e o fallback síncrono; a PR #24 extraiu a persistência de turnos para `core/harness_turn.py`, preservando o wrapper do Harness, o `chat_id` atual, o registro síncrono, a filtragem de texto vazio e o log de erro sem derrubar a tarefa; a PR #25 extraiu a garantia de sessão para `core/harness_session.py`, preservando a reutilização/criação da sessão, o controle de `_chat_started_here`, o vínculo ao `ContextVar` atual e o retorno do `chat_id`; a PR #26 extraiu o encerramento de sessão para `core/harness_session.py`, preservando o `CHAT_END`, a limpeza condicional do `ContextVar`, o reset de `_session` e `_chat_started_here`, a limpeza de redaction e a execução da limpeza em `finally`; a PR #27 extraiu o registro da resposta do modelo para `core/harness_model.py`, preservando o registro no `TaskTrace`, o tratamento de falha da instrumentação com `TRACE_ERROR`, o evento `MODEL_ROUND_RESPONSE`, o arredondamento da latência e o repasse de dados extras; a PR #28 extraiu a execução das ferramentas de cada rodada para `core/harness_tools.py`, preservando cancelamento, passos no `TaskManager`, logs, `ToolResult`, trace por ferramenta, invalidação de geometria visual, histórico, contadores e estado de falha; a PR #29 extraiu o tratamento de rodadas sem chamadas de ferramenta para `core/harness_guards.py`, preservando retry da primeira rodada para ações, falha por ação não executada, guards visual e multitab, contadores, transições de espera/retomada e retorno direto após erro do provider; a PR #30 extraiu a finalização de resposta final bem-sucedida para `core/harness_completion.py`, preservando o callback `apos_tarefa`, a composição da resposta, a persistência da estratégia, a conclusão do TaskManager, o registro do turno e o log `TASK_STATE`, mantendo no Harness o retry de resposta vazia e o controle do ciclo; a PR #31 extraiu o retry de resposta vazia para `core/harness_completion.py`, preservando o limite de uma tentativa, montagem do estado de retry, cancelamento, `tool_choice`, espera/retomada do TaskManager, logs, chamada ao modelo e retorno direto após erro do provider; a PR #32 extraiu a conclusão local após execução bem-sucedida de ferramenta para `core/harness_completion.py`, preservando os logs `TASK_LOCAL_COMPLETION`/`TASK_END`, o callback `apos_tarefa`, a persistência da estratégia, a conclusão do TaskManager, o registro do turno e a criação da resposta; a PR #33 extraiu a decisão determinística de conclusão local para `core/harness_heuristics.py`, preservando o wrapper compatível no `AurenHarness`, as constantes de ferramentas e o critério de sucesso baseado em `item.get("sucesso")`; a PR #34 extraiu a mecânica operacional comum das rodadas do modelo para `core/harness_model.py`, preservando `_pedir_modelo` como único ponto de chamada ao provider, a ordem espera/log/chamada/log/resume e o tratamento de erro no Harness; a PR #35 extraiu a execução e finalização do fast path para `core/harness_fast_path.py`, preservando o trace, steps, turnos, logs, falhas, cancelamento, conclusão e retorno ao ciclo normal; a PR #36 extraiu a preparação do input da próxima rodada para `core/harness_round_input.py`, preservando a montagem existente de function calls, function_call_output, imagens, geometria e o estado textual efetivamente enviado; o item 5 foi encerrado nesta rodada; Windows, Browser e Harness foram separados em módulos de domínio com PRs pequenos e CI verde.

## O que a PR #6 entrega

- conversão centralizada de coordenadas de imagem para coordenadas físicas/globais do Windows
- vínculo da geometria ao snapshot visual observado
- validação de resize/compressão, escala, aspect ratio, origem negativa e limites
- bloqueio de snapshot inexistente, antigo ou inseguro
- exigência de contexto DPI verificável para transformação visual
- invalidação do snapshot depois de ação visual bem-sucedida
- exigência estrutural de nova observação antes de concluir após mudança visual
- cobertura integrada captura -> geometria -> Dispatcher -> conversão -> execução
- correções de regressões da suíte e do CI

## Capacidades já concluídas ou presentes

- contratos, Router, Dispatcher, PermissionManager e ToolResult
- memória persistente em SQLite
- browser com abas/sessão persistente
- automação Windows
- busca e inteligência inicial de arquivos
- visão de tela
- clique visual
- arraste visual
- verificação de estado em tarefas visuais compostas
- voz local-first

## Próxima fase — ainda não iniciada

**Estabilização e limpeza pós-V47**

Objetivo: alinhar versão, documentação, testes, observabilidade e estado do projeto depois do merge da V47.

Critérios de saída:

- [x] README.md representa a versão real
- [x] versão/config/facade estão sincronizados
- [x] estado oficial atualizado
- [x] documentação antiga claramente separada de documentação normativa
- [x] suíte completa validada na main
- [x] trace persistente por tarefa implementado e validado na PR #8
- [x] validação visual Windows do merge mais recente concluída
- [ ] nenhuma regressão conhecida pendente

## Depois da estabilização

Próxima grande capacidade planejada:

**Browser Intelligence**

Objetivo: permitir que Auren entenda o contexto do navegador (abas, página ativa, conteúdo/estrutura relevante), aja usando as ferramentas existentes e verifique o resultado.

Esta fase só começa quando a estabilização pós-V47 estiver encerrada.

## Backlog futuro

Ideias futuras não fazem parte da tarefa atual:

- memória contextual/semântica mais avançada
- inteligência geral do Windows
- multi-device
- terminal no celular
- ESP32/Arduino
- integração com Minecraft
- wake word e experiências avançadas de voz
- interface visual estilo Jarvis

A presença de um item neste backlog **não autoriza iniciar sua implementação** enquanto a tarefa atual não estiver concluída.

## Regras de continuidade

### Uma tarefa ativa

O projeto deve ter uma única **Tarefa atual**. Todo o resto é concluído, próxima fase ou backlog.

### Estado verificável

Sempre que este arquivo for consultado, comparar:

- versão declarada em config.py/auren.py
- branch e PR ativas
- head commit
- resultado do CI
- estado real da main

Se houver divergência, corrigir o estado antes de iniciar trabalho novo.

### Toda mudança relevante atualiza o estado

Quando uma PR mudar comportamento, arquitetura, capacidade, versão ou próximo passo, o estado oficial deve ser atualizado na mesma transição.

### Sem expansão silenciosa de escopo

Uma ideia nova pode ir para o backlog. Ela só vira tarefa atual quando a tarefa anterior estiver encerrada ou quando for comprovado que ela é um bloqueador real.

### Histórico não é estado

Commits, PRs, relatórios de auditoria e versões antigas explicam o passado. Este arquivo descreve **onde o projeto está agora e qual é o próximo passo**.

## Fonte de continuidade

AUREN_STATE.md -> branch/PR -> CI -> tarefa atual -> implementação -> testes -> atualização deste arquivo