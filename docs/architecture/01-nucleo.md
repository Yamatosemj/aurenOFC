# Arquitetura 01 — Nucleo de execucao, ciclo do Harness e tarefas

LIV-006 (correção candidata): no ciclo do modelo, um veto permite no máximo uma proposta alternativa dentro do orçamento existente. Assinaturas vetadas não podem ser executadas, mesmo que uma revisão posterior mude de opinião. A alternativa mantém revisor, Dispatcher e permissões. Novo veto ou falta de alternativa encerra com falha. Atalhos locais vetados continuam sem replanejamento.

> **Escopo:** auditoria estatica do codigo da main em 2026-10-10, revisao de testes automatizados e verificacao de CI desta PR. Este texto documenta a **implementacao observada**, nao promete desempenho real, operacao de hardware nem ausencia de defeitos.
>
> **Referencia auditada:** commit base da etapa 1: 525670c342b3aefb026b44d9ff5a4d2a250fbd9b. Consulte a main atual para mudancas posteriores.
>
> **Situacao:** documentacao tecnica do nucleo auditada estaticamente. Execucao Live, cancelamento de chamadas externas bloqueadas e tarefas de Windows/navegador/modelo reais **nao** foram validados nesta etapa.

## 1. Escopo e limites de responsabilidade

O Auren possui **um ciclo operacional central de tarefas**, cuja coordenacao pertence a [AurenHarness](../../core/harness.py) e ao helper [harness_cycle.executar_ciclo](../../core/harness_cycle.py). A separacao em varios arquivos nao significa varios executores independentes.

**Cuidado com os nomes semelhantes:**

| Componente | Papel comprovado pelo codigo | Nao confundir com |
| --- | --- | --- |
| [auren.criar_harness](../../auren.py) | Fabrica e ponto de composicao usado por canais: injeta callbacks de modelo, ferramentas, atalhos, permissoes, contexto e metricas | Uma segunda implementacao do ciclo |
| [AurenHarness](../../core/harness.py) | Coordenacao por mensagem, estado da sessao, preparacao do contexto, fast path, ciclo, cancelamento, finalizacao e trace | Um executor que possa pular permissoes |
| [harness_cycle.executar_ciclo](../../core/harness_cycle.py) | **Dono da decisao de continuar/finalizar**: rodada do modelo, ferramentas, guards e conclusao | Apenas uma chamada ao modelo |
| [agent.AgentOrchestrator](../../agent/orchestrator.py) e [PlanBuilder](../../agent/planner.py) | Plano **local, heuristico**, classifica complexidade, produz estimativa de rodadas; nao chama outro LLM | [core.AurenOrchestrator](../../core/orchestrator.py) |
| [core.AurenOrchestrator](../../core/orchestrator.py) | Router seleciona conjunto de tools e provider executa chamada ao modelo; cache restrito de respostas estaveis | Planner local ou dono do loop |
| [TaskManager](../../core/task_manager.py) | Fonte de estados **em memoria** de tarefa ativa, passos, historico recente e cancelamento solicitado | Agendador autonomo ou banco persistente de tarefas |
| [SessionContextManager](../../core/session.py) | Compoe contexto do chat a partir de turnos, tarefas recentes, memoria e skills | TaskManager, trace ou sessao do provider |
| [TaskTraceStore](../../core/task_trace.py) | Telemetria observacional persistida **em SQLite separado** | Memoria conversacional |
| [AgentTaskQueue](../../agent/ari_native/task_queue.py) | Fila de trabalho auxiliar, usada no Harness para persistencia de estrategia **pos-tarefa** | Fila de comandos de usuario ou segundo ciclo |
| [harness_runtime](../../core/harness_runtime.py) | Contexto de logs por chat, logs de tarefa e redacao; usa ContextVar de sessao | Estado operacional da tarefa |

O nucleo **nao** deve criar ferramentas paralelas. Em chamadas normais e atalhos locais, a rota autorizada passa por [tools/dispatcher.py](../../tools/dispatcher.py): validacao de argumentos e contrato, preflight especial quando aplicavel, [PermissionManager](../../core/permission_manager.py), handler e [ToolResult](../../core/tool_result.py). Uma auditoria completa dessas politicas pertence a **Etapa 2**.

## 2. Mapa do fluxo real

~~~mermaid
flowchart TD
    A["Canal (CLI / GUI / voz)"] --> B["auren.criar_harness()"]
    B --> C["AurenHarness.processar_mensagem()"]
    C --> D["Sessao + Contexto + TaskManager + TaskTrace"]
    D --> E{"Atalho local tratado?"}
    E -->|sim| F["Router.decidir_local -> tools/fast_paths -> Dispatcher"]
    F --> G["Registrar passo e concluir / falhar / cancelar"]
    E -->|nao| H["harness_cycle.executar_ciclo"]
    H --> I["core.AurenOrchestrator -> Router.select_tools -> Provider"]
    I --> J{"function_call?"}
    J -->|sim| K["harness_tools: executar_ferramenta -> Dispatcher"]
    K --> L["ToolResult + passos + guards visual/browser"]
    L --> M{"Conclusao local segura?"}
    M -->|sim| N["TaskManager.complete + resposta"]
    M -->|nao| I
    J -->|nao| O["Guards / resposta vazia / finalizacao"]
    O --> N
    G --> P["Trace finalizado no finally"]
    N --> P
~~~

O diagrama e **simplificado**: erro do provider, limites e cancelamento levam a estados de falha/cancelamento, nao necessariamente a conclusao. O Router tem dois usos distintos: decidir se existe um atalho local e selecionar ferramentas disponiveis para a chamada ao modelo.

### Caminho concreto, na ordem de execucao

1. **Composicao:** [auren.py](../../auren.py) cria o Harness com callbacks de [core/response.py](../../core/response.py), executor do Dispatcher, atalho local, PermissionManager e SessionContextManager. No modo de teste AUREN_TEST_MODE=1, a fabrica configura **max_model_rounds=8**.
2. **Inicio:** **processar_mensagem** garante sessao, vincula a ContextVar e delega para **_processar_mensagem_impl**. O callback de inicio da tarefa reinicia limites de permissao; a geometria visual e os marcadores de verificacao sao limpos.
3. **Planejamento/contexto:** **agent.begin(objetivo)** prepara um plano local; **context.build(chat_id, objetivo, tarefas=recent_snapshots(...))** monta o contexto. Erros dessa preparacao sao registrados, com fallback de contexto vazio; isso nao confirma sucesso da consulta de memoria.
4. **Rastro operacional:** TaskManager cria/inicia um TaskSnapshot com chat_id; TaskTraceStore tenta iniciar trace; o turno de usuario e registrado quando existe persistencia. Falha ao iniciar trace e isolada/logada.
5. **Atalho:** **_executar_fast_path** solicita decisao ao Router por [tools/fast_paths.py](../../tools/fast_paths.py); quando tratado, registra passo e estado terminal sem entrar no loop de modelo. A classificacao de sucesso do fast path adapta retornos textuais legados; **nao** e a mesma mecanica de avaliacao estrutural do loop.
6. **Primeira rodada do modelo:** **harness_cycle** monta estado com objetivo e contexto controlado; quando reconhece pedido de acao, utiliza tool_choice=required. **_executar_rodada_modelo** gerencia WAITING/RUNNING, telemetria e invoca **harness._pedir_modelo**, que centraliza tratamento de falhas do provider.
7. **Rodadas seguintes:** sem previous_response_id. O input da rodada seguinte inclui o **estado compacto**, as chamadas function_call da resposta imediatamente anterior e os outputs correspondentes; imagens e geometria podem ser inseridas em mensagem de usuario. Veja [harness_round_input.py](../../core/harness_round_input.py) e [harness_state.py](../../core/harness_state.py).
8. **Ferramentas:** [harness_tools.py](../../core/harness_tools.py) inicia passo, chama o executor injetado, converte o retorno para ToolResult e registra o resultado. Sucesso da ferramenta no loop e determinado por **ToolResult.ok**, nao por texto positivo da mensagem. Erros de excecao no callback viram ToolResult.failure.
9. **Continuacao ou fim:** o ciclo consulta cancelamento, pendencias de verificacao, heuristica de conclusao local e respostas sem tool calls; completa, falha ou cancela a tarefa. Apos resposta bem-sucedida, pode registrar estrategia em fila de fundo e turno de assistant.
10. **Finalizacao de telemetria:** **processar_mensagem** possui finally que finaliza trace e restaura o contexto de sessao mesmo em excecoes. O CLI fecha a sessao e fila ao sair; outros canais devem implementar seu ciclo de vida adequadamente.

### Contratos de chamada que um mantenedor precisa preservar

- **AurenHarness.processar_mensagem(mensagem)** devolve uma tupla **(tratado_rapido, resposta)**. Quando tratado_rapido e True, o valor pode ser texto do atalho ou wrapper; no caminho normal o retorno expoe **output_text**. Os consumidores devem respeitar ambos os formatos — ver [harness.py](../../core/harness.py) e [tests/test_task_manager.py](../../tests/test_task_manager.py).
- **AurenHarness._executar_ciclo** delega a [harness_cycle.executar_ciclo](../../core/harness_cycle.py), sem segundo loop. Nao introduza uma chamada direta de provider em GUI, voz, fast path ou outro componente.
- **TaskManager** oferece snapshots imutaveis (dataclasses frozen, com steps em tupla), mas gerencia os registros internos com RLock. Nao mutar snapshots como se fossem fonte persistente.
- **Dispatcher** retorna ToolResult estruturado; a conversao **from_legacy** e ponte de compatibilidade, nao especificacao para ferramentas novas.
- As interfaces da camada de voz e GUI usam a **mesma fabrica** para o Harness; nao criam atalho para executar tools.

## 3. Estados de tarefa e semantica do cancelamento

A fonte autoritativa e [core/task_manager.py](../../core/task_manager.py).

~~~text
CREATED -> RUNNING -> WAITING -> RUNNING -> ...
   |         |          |
   +---------+----------+--> FAILED ou CANCELLED
             |
             +---------------> COMPLETED
~~~

Estados terminais: **COMPLETED**, **FAILED** e **CANCELLED**. A transicao de qualquer estado terminal para outro estado e rejeitada; repetir o mesmo estado e permitido pelo helper interno de transicao, mas operacoes publicas de conclusao/falha nao aceitam tarefa terminal.

- **create()** rejeita nova tarefa enquanto a atual nao for terminal, atribui ID e chat_id; historico e limitado por **max_history=100** (padrao), com limpeza preferencial de tarefas terminais antigas.
- **start()**, **wait_for_model()** e **resume()** controlam CREATED/RUNNING/WAITING.
- **begin_step()/finish_step()** registram nome, argumentos, tentativa, sucesso, resultado e erro de cada ferramenta; os metodos sao protegidos pelo lock do manager.
- **complete()/fail()/cancel()** sao terminais. Se o cancelamento ja foi solicitado, complete ou fail transforma a tarefa em CANCELLED.
- **request_cancel()** marca flag cooperativa; **should_cancel()** e consultado antes de rodadas, entre chamadas e antes de conclusoes locais; **cancel_current_task()** devolve False quando nao ha tarefa ativa.
- **Nao ha rollback implicito:** cancelamento nao interrompe necessariamente uma chamada externa ja em execucao, nem desfaz cliques, arquivos ou mudancas no Windows. A UI tambem nao garante cancelamento instantaneo.
- **Nao ha agendamento persistente por TaskManager:** memoria SQLite conversacional, traces SQLite e fila de estrategia sao mecanismos diferentes. Nao vender "retomar tarefa depois de reiniciar" como capacidade deste manager.

## 4. Continuidade, verificacao e encerramento

### Contexto e historico

[harness_state.py](../../core/harness_state.py) limita o **estado textual compacto a 4500 caracteres** (configurado no Harness), conserva os **2** itens recentes do historico de ferramentas e usa **contexto completo somente na primeira rodada**. O contexto de sessao e limitado adicionalmente pelo SessionContextManager; recebe historico, fatos, memoria, estrategias e skills conforme disponibilidade e politicas.

[harness_round_input.py](../../core/harness_round_input.py) evita reutilizar a cadeia inteira de respostas. Nao utiliza previous_response_id. Isso **nao e memoria infinita**: historicos mais antigos podem ser omitidos dos prompts; somente armazenamento e recuperacao de contexto permitem continuidade entre conversas.

### Regra para concluir localmente

O ciclo pode dispensar nova chamada ao modelo quando a ultima etapa solicitada foi cumprida, ToolResult.ok indica sucesso e **nao ha verificacao visual/browser pendente ou falha nao recuperada**. O criterio exato esta em [harness_heuristics.py](../../core/harness_heuristics.py), incluindo lista explicita de ferramentas terminais e verificacao de abas numeradas. Nao adicionar "conclusao rapida" noutro lugar.

### Guards e falhas

**Fechamento total e respostas de esclarecimento (PR #139, candidata):** no mesmo chat, uma resposta afirmativa estritamente reconhecida (incluindo "ja disse que sim") retoma o objetivo original e o estado controlado registra que a pergunta de **escopo** ja foi respondida. Se o modelo repetir uma pergunta equivalente de confirmacao de fechamento total, o Harness exige uma proxima chamada de ferramenta apenas uma vez; se persistir, falha sem executar efeitos adicionais. Isso **nao** autoriza ferramentas: revisao de intencao, contratos e PermissionManager permanecem obrigatorios. Apos toda tentativa de `encerrar_processo_windows` num pedido de fechamento completo, o ciclo exige `listar_processos_windows` filtrada pelo alvo antes de propor outro PID; listas antigas ou falhas nao contam, e encerramentos em lote sao rejeitados. `taskkill` sozinho nao prova resultado final. Regressao em `tests/test_steam_live_followup_20261013.py` com mocks; teste Live posterior e decisao separada.


- **Visual:** apos ferramenta visual mutante bem-sucedida com geometria ativa, o Harness invalida a geometria e exige nova observacao antes de encerrar certas tarefas. Guard tenta novamente ate o limite implementado.
- **Browser:** em tarefas compostas identificadas heurísticamente, mudanca de estado deixa verificacao pendente; **obter_contexto_navegador** so libera a pendencia com evidência deterministica positiva, segundo [browser_verification.py](../../core/browser_verification.py).
- **Multitab:** confirma destinos reconheciveis de abas numeradas e limita retries; nao se aplica genericamente a toda navegacao.
- **Resposta vazia:** tenta uma recuperacao especifica e pode falhar com **empty_response**.
- **Pedido de acao sem ferramenta:** forca uma tentativa com tool_choice=required e pode falhar com **action_not_executed**.
- **Falha de ferramenta:** nao reexecuta cegamente as chamadas da mesma rodada; pode solicitar nova decisao do modelo e falhar com **step_failed_unrecovered**.
- **Erro de provider:** **_pedir_modelo** falha a tarefa com **provider_error**, devolve None e o ciclo responde com mensagem controlada.
- **Limite nominal:** **DEFAULT_MAX_MODEL_ROUNDS=12**; planejador heuristico pode sugerir 15 ou 18, e a heuristica local pode elevar profundidade. Valor configurado **abaixo de 12 e teto de iteracoes da estrutura principal**. Isso nao deve ser prometido como limite absoluto de chamadas ao provider: helpers de guard/retry tambem fazem chamadas e precisam ser contabilizados em qualquer auditoria de custo.

O campo **agent.state.phase** do planejador local nao constitui o estado terminal operacional: no fluxo do ciclo, o estado real vem do TaskManager. Os metodos complete/fail/cancel do AgentOrchestrator **nao sao o mecanismo decisor do loop**.

## 5. Persistencia, telemetria e privacidade

| Area | Caminho e natureza | Garantia observada |
| --- | --- | --- |
| Tarefas | [TaskManager](../../core/task_manager.py) — registros na memoria do processo | Estados/snapshots, sem recuperacao automatica apos reinicio |
| Contexto conversacional | [SessionContextManager](../../core/session.py), [memory/store.py](../../memory/store.py) | Consulta/registro quando storage esta configurado; isolamento por chat_id nos metodos correspondentes |
| Estrategias de sucesso | [harness_strategy.py](../../core/harness_strategy.py), [AgentTaskQueue](../../agent/ari_native/task_queue.py) | Persistencia em worker apos a tarefa, ou fallback sincrono em erro de fila; nao e agendador principal |
| Traces | [TaskTraceStore](../../core/task_trace.py) — data/traces/auren_trace.sqlite3 | Hash do objetivo, duracao, tokens, custo estimado, etapas e status |
| Logs por chat/tarefa | [harness_runtime.py](../../core/harness_runtime.py) — logs/chats e logs/tarefas, mais log legado | Log textual com redacao de campos/conteudos sensiveis; nao assumir que toda informacao arbitraria esta protegida |
| Sessao corrente | ContextVar em [harness_runtime.py](../../core/harness_runtime.py) | Contexto de execucao para logs; distinto de TaskManager.current_snapshot |

Os traces sao observacionais: nao representam um mecanismo para reproduzir comandos antigos ou reexecutar uma tarefa. Falhas ao gravar spans sao toleradas; falhas da persistencia principal de trace podem ser registradas sem impedir o processamento. Nao registrar tokens, segredos, clipboard bruto ou conteudo sensivel em novos logs; confira [harness_logging.py](../../core/harness_logging.py) antes de adicionar campos.

## 6. Matriz de testes e evidencia

**Foram lidos o codigo do caminho critico e os testes abaixo**; eles usam predominantemente callbacks, stores temporarios e ferramentas simuladas. A lista cobre o contrato documentado, **nao equivale a teste real da interface/Windows/API**.

| Contrato | Arquivos de teste principais | O que o teste simula/verifica |
| --- | --- | --- |
| Dono unico do ciclo, rodadas, ordenacao, limite, ToolResult, falhas e cancelamento | [test_harness_loop_owner.py](../../tests/test_harness_loop_owner.py), [test_harness_cycle_module_boundary.py](../../tests/test_harness_cycle_module_boundary.py) | Respostas e calls artificiais, ciclos e invariantes |
| Request/response do modelo e telemetria da rodada | [test_harness_model.py](../../tests/test_harness_model.py) | Sequencia WAITING, log, trace, falha |
| Resultados de ferramentas e verificação visual/browser | [test_harness_tools.py](../../tests/test_harness_tools.py), [test_harness_guards.py](../../tests/test_harness_guards.py) | ToolResult, pendencias, retries, bloqueio de conclusao |
| Resposta final e retry vazio | [test_harness_completion.py](../../tests/test_harness_completion.py) | Finalizacao local/modelo, memoria opcional, retries |
| Reconstrucao de input e geometria | [test_harness_round_preparation.py](../../tests/test_harness_round_preparation.py), [test_vision_input.py](../../tests/test_vision_input.py) | Function outputs, imagem e contexto |
| Estados, transicoes e cancelamento | [test_task_manager.py](../../tests/test_task_manager.py), [test_task_manager_terminality.py](../../tests/test_task_manager_terminality.py), [test_cancellation_harness.py](../../tests/test_cancellation_harness.py) | Rejeicao de estados terminais e cancelamento cooperativo |
| Traces | [test_task_trace.py](../../tests/test_task_trace.py) | SQLite temporario, spans e metricas |
| Sessoes e memoria escopada | [test_session_context.py](../../tests/test_session_context.py), [test_session_isolation.py](../../tests/test_session_isolation.py) | Isolamento entre chats, contexto, compatibilidade |
| Dispatcher/roteamento em um caminho | [test_execution_single_path.py](../../tests/test_execution_single_path.py), [test_routing_single_owner.py](../../tests/test_routing_single_owner.py) | Contratos, permissoes e callbacks simulados |
| Fila de trabalho auxiliar | [test_task_queue_lifecycle.py](../../tests/test_task_queue_lifecycle.py), [test_ari_integration.py](../../tests/test_ari_integration.py) | Shutdown, duplicacao, excecoes e plano local |
| Limites de modulo e compatibilidade | [test_harness_runtime_module_boundary.py](../../tests/test_harness_runtime_module_boundary.py), [test_harness_session.py](../../tests/test_harness_session.py) | Reexports e ownership de sessao/log |

**CI desta PR:** registrar no comentario/resultado da PR o SHA, jobs e numeros apos execucao. Nao inserir neste texto uma quantidade de aprovados que envelhece a cada nova mudanca. Para situacao mais recente consulte [AUREN_STATE.md](../../AUREN_STATE.md) e Actions.

## 7. Pontos encontrados para investigacao futura (sem alteracao de runtime)

Estas sao **observacoes de leitura estatica**, nao laudos de vulnerabilidade nem declaracao de falha reproduzida:

1. **Continuação de itens de reasoning (achado 7, correção candidata).** [harness_round_input.py](../../core/harness_round_input.py) passa a preservar itens de tipos `reasoning` e `function_call` **somente da rodada anterior, na ordem original**, antes dos respectivos `function_call_output`. [Testes offline](../../tests/test_harness_reasoning_continuity.py) verificam objeto, ordem e payload ao provider simulado. O Harness ainda usa `reasoning_effort="none"` e `previous_response_id=None`: esta correção não habilita raciocínio extra nem prova aceitação real pela API.
2. **Falhas pendentes entre ferramentas e rodadas.** [harness_tools.py](../../core/harness_tools.py) conserva cada falha por ferramenta e assinatura privada dos argumentos originais. Outra acao bem-sucedida nao a apaga; repetir a mesma operacao com sucesso a recupera. A assinatura e separada do texto mascarado dos logs. Alternativas semanticamente equivalentes continuam sem reconhecimento automatico. Veja o [relatorio de correcoes](../../RELATORIO_CORRECOES.md).
3. **Contagem de rodadas versus chamadas reais.** [harness_cycle.py](../../core/harness_cycle.py) usa um loop limitado, mas [harness_guards.py](../../core/harness_guards.py) e [harness_completion.py](../../core/harness_completion.py) possuem tentativas internas de provider. Validar contagem efetiva ao definir limites de custo e timeout externos.
4. **Estado do AgentOrchestrator.** [agent/orchestrator.py](../../agent/orchestrator.py) expoe fases completas/falhas, mas o ciclo usa efetivamente [TaskManager](../../core/task_manager.py). Nao utilizar agent.state.phase como evidencia de conclusao sem verificar sincronizacao.
5. **Operacoes externas nao reversiveis automaticamente.** Cancelamento, excecao ou queda de processo nao implicam rollback. Validar integracao especifica com UI/Windows apenas quando houver autorizacao para testes Live.

Registrar uma hipotese como tal e mais util do que alterar o codigo sem testes reproduziveis. Se alguma dessas observacoes justificar acao, abrir **tarefa e PR isoladas**, sujeitas a prioridade do proprietario.

## 8. Guia de manutencao segura

**Para trocar o modelo ou provider:** revisar [core/response.py](../../core/response.py), [core/orchestrator.py](../../core/orchestrator.py), [providers/openai_provider.py](../../providers/openai_provider.py), o formato de output e [harness_round_input.py](../../core/harness_round_input.py). Conferir reasoning, function_call_output, chamadas vazias e tratamento de falhas. Nao alterar Router ou Dispatcher por reflexo.

**Para mudar regras de fim/retry:** revisar [harness_cycle.py](../../core/harness_cycle.py), [harness_heuristics.py](../../core/harness_heuristics.py), [harness_guards.py](../../core/harness_guards.py), [harness_completion.py](../../core/harness_completion.py); exigir testes para falha de tool, guard, cancelamento e contagem de rodadas. Nao introduzir outro loop.

**Para melhorar cancelamento:** revisar [TaskManager](../../core/task_manager.py), seus pontos de consulta no ciclo e consumidores GUI/voz. Diferenciar pedido cooperativo de interrupcao forçada e de rollback.

**Para ampliar a memoria:** preservar isolamento por chat e fronteira [SessionContextManager](../../core/session.py); nao converter TaskManager em armazenamento duravel sem projeto especifico.

**Para adicionar ferramentas:** partir do registry, contrato, Dispatcher, PermissionManager, ToolResult e testes end-to-end simulados — essa responsabilidade sera detalhada na **Etapa 2**.

**Para refatorar o Harness:** preservar callbacks publicos, **processar_mensagem**, ownership do ciclo, logs/trace, estado de tarefa, ContextVar, compatibilidade do retorno (bool, valor), fluxo de imagem e callbacks de memoria. O PR aberto #54 de refatoracao **nao esta automaticamente integrado ou aprovado**; conferir diff contra a main antes de reaproveitar ideias.

**Checklist minimo de PR:** arquivos e consumidores lidos; mudanca limitada; efeitos colaterais explicados; pytest e CI identificados por SHA; limites nao testados declarados; arquitetura/estado documental atualizados; sem Live/Windows/API nao autorizados.


## Revisão semântica de intenção (PR #132)

No caminho de execução pelo modelo, antes de despachar uma rodada com ferramentas que podem alterar estado, `core/harness_cycle.py` invoca a verificação semântica de `core/intent_verification.py` pelo `OpenAIProvider`. A verificação recebe pedido original, nomes/argumentos propostos e histórico recente, mas **nenhuma ferramenta**. Decisões válidas: aprovar, esclarecer (pergunta ao usuário antes da execução) ou bloquear; erro, resposta malformada ou indisponibilidade bloqueiam a execução da rodada. O PermissionManager e as validações de contratos continuam soberanos. Leituras definidas como não mutáveis evitam a chamada extra. O verificador não prova sucesso: resultados de navegação/visão seguem os guards e evidências existentes, e ferramentas sem leitura pós-ação continuam sujeitas aos limites de observabilidade conhecidos. Os atalhos locais executáveis também são planejados sem efeitos por `tools/fast_paths.py::planejar_comando_rapido` e passam por esta guarda antes do Dispatcher. O experimento de áudio opt-in mantém sua política separada e não é coberto por este guard. A qualidade da decisão semântica ainda requer testes Live autorizados; testes unitários com mocks não bastam.


### Correção: verificação proporcional de intenções simples

`core/intent_verification.py::proposta_simples_exata` reconhece **somente** solicitações explícitas e de argumento integralmente correspondente: ajuste de volume com percentual exato; mudo explícito; controle de mídia não alternável (próxima, anterior, parar); site/URL explicitamente nomeados com navegação visível; quantidade exata de abas em branco; e abertura explícita de aplicativo pelo nome. Nenhuma tool, argumento ou ação adicional pode aparecer, e o histórico da tarefa precisa estar vazio. A ferramenta é selecionada pelo fluxo existente; essa função apenas dispensa uma revisão semântica **adicional**, não decide ou autoriza a ação. Ações com efeito mais complexo, nomes incertos, operações compostas, mídia com `play_pause` (alterna estados), ou proposta distinta do pedido continuam submetidas à verificação pela IA. O resultado pós-ação, o Dispatcher, os contratos e as permissões permanecem inalterados. Os testes de unidade não substituem validação real da API e do Windows.
