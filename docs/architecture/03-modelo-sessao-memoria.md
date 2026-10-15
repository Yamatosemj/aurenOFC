# Arquitetura 03 — Modelo, sessão, contexto e memória

> **Etapa 3:** auditoria do código no commit `a4ddb8a9f01b0cefa0d7233ac8714d4539a8502b`, em 2026-10-10. Escopo documental: implementação, consumidores, testes e reproduções locais com dados sintéticos. Nenhuma mudança de runtime.
>
> O [núcleo](01-nucleo.md) controla o ciclo; o [caminho de ferramentas](02-roteamento-seguranca.md) valida e autoriza ações. Este documento explica o que chega ao modelo, o que persiste e o que pode ser recuperado. **Persistir não significa recordar tudo nem retomar tarefas automaticamente.**

## 1. Responsabilidades e pontos de entrada

| Componente | Responsabilidade observada |
| --- | --- |
| [auren.py](../../auren.py) | Compõe um store SQLite e um SessionContextManager compartilhados no processo; a fábrica injeta esse contexto no Harness |
| [core/response.py](../../core/response.py) | Fachada compatível com API antiga; mantém um AurenOrchestrator de módulo, expõe cliente e métricas |
| [core/orchestrator.py](../../core/orchestrator.py) | Consulta cache elegível, seleciona tools pelo Router e chama o provider; não executa tools |
| [providers/openai_provider.py](../../providers/openai_provider.py) | Cria cliente SDK sob demanda, monta Responses e registra uso |
| [core/session.py](../../core/session.py) | Monta ContextSnapshot, registra turnos e estratégias através do store |
| [core/memory_context.py](../../core/memory_context.py) | Extrai termos e recupera conversas/estratégias por busca lexical; mantém helper textual de compatibilidade |
| [memory/store.py](../../memory/store.py) | SQLite: fatos, conversas e estratégias; valida dados, filtra termos de credenciais e consulta registros |
| [tools/memory.py](../../tools/memory.py) | Wrappers JSON das três ferramentas de fatos; o Dispatcher adapta o retorno para ToolResult |
| [core/harness_runtime.py](../../core/harness_runtime.py) | Identidade de chat e contexto de logs; diferente da composição de memória |
| [core/usage.py](../../core/usage.py) | Contadores globais do processo e custo estimado com coeficientes fixos |

A cadeia oficial continua passando pelo Harness. Métodos Python públicos de store/provider são APIs internas; não representam novas ferramentas autorizadas ao modelo.

## 2. Contrato do provider e configuração

[OpenAIProvider.create_response](../../providers/openai_provider.py) envia `model`, `instructions`, `tools`, `input`, `parallel_tool_calls=False`, `reasoning.effort`, `prompt_cache_key` e `prompt_cache_options={"ttl": "30m"}`. Acrescenta `tool_choice` se fornecido e `previous_response_id` se o argumento `response_id` for verdadeiro.

- `tools=None` significa registry completo por compatibilidade. `tools=[]` continua vazio; não recebe fallback automático.
- O cliente é lazy e reutilizado na instância. Só com `AUREN_TEST_MODE=1`, sua criação recebe `timeout=45.0` e `max_retries=0`; na produção o adaptador deixa essas opções aos defaults do SDK instalado.
- A flag de teste **não impede chamadas de API**. Os testes desta etapa usam callbacks/clientes falsos; não dependem da flag como bloqueio de rede.
- O provider devolve o objeto da resposta. Os consumidores esperam atributos como `output`, `output_text`, `usage` e itens `function_call`. Isso é uma fronteira de adaptação, não prova de portabilidade para qualquer SDK.
- Exceção capturada por `AurenHarness._pedir_modelo` marca a tarefa com `provider_error` e devolve mensagem controlada. A próxima tarefa pode funcionar; não existe fallback automático para outro modelo nesse adaptador.
- Os parâmetros acima descrevem **o payload do código**, não uma validação de aceitação, preços ou retenção do serviço remoto.

### Modelo: diferença entre configuração e inicialização

[config.py](../../config.py) lê `AUREN_MODEL` no import, remove espaços e usa `gpt-5.6-luna` quando vazio. **Correção candidata do achado 4:** [auren.py](../../auren.py) conserva o literal de **modelo padrão** para descoberta estática/compatibilidade, mas valida esse literal contra `config.DEFAULT_MODEL` e, depois, define o modelo efetivo a partir de `config.MODEL`. Dessa forma, um override legítimo não interrompe a importação; coerência de versão/cache/arquitetura/default continua exigida. A aceitação do identificador pela API depende da conta e da disponibilidade do modelo.

O [prompt](../../core/prompt.py) agora inclui o identificador realmente configurado em vez da identidade textual fixa; serializa o nome como string JSON para não transformar quebras de linha/aspas vindas do ambiente em linhas de instrução. [test_model_config.py](../../tests/test_model_config.py) mantém os testes antigos; [test_model_override_startup.py](../../tests/test_model_override_startup.py) adiciona import completo em subprocesso, isolamento de SQLite, provider simulado sem rede e preservação da descoberta estática. **Não** é prova de que um ID arbitrário exista ou seja compatível na API.

## 3. Sessão, chat e contexto da tarefa

Cada Harness guarda seu `SessionContext(chat_id, log_file)`. A criação gera identificador temporal e pasta exclusiva; chamadas seguintes reutilizam a sessão daquele Harness. O binding corrente de logs usa ContextVar. Fechar a sessão limpa o vínculo/estado de sessão e redactions, **não apaga o SQLite nem constitui retomada de histórico**. Novos Harnesses normalmente recebem novos IDs.

[SessionContextManager](../../core/session.py) é compartilhado pela fábrica, mas a consulta recebe o ID de cada Harness. Compartilhar o objeto não significa compartilhar automaticamente turnos entre IDs. Também não basta reabrir o programa para recuperar a conversa anterior: não há restauração automática do ID nessa criação.

Na preparação de cada mensagem, o Harness:

1. Garante a sessão e reinicia os controles da tarefa.
2. Chama `context.build(chat_id, objetivo, tarefas=recent_snapshots(chat_id, limit=3))`.
3. Guarda o texto do snapshot, cria a tarefa/trace e registra o turno do usuário.
4. Tenta o atalho local; se necessário, entra no ciclo do modelo.

A ordem evita incluir o pedido atual duas vezes como turno recente e objetivo. O atalho também registra a resposta do assistant. Nos caminhos de sucesso do ciclo, a resposta final é registrada; mensagens de erro/cancelamento não possuem uma garantia geral de registro como turno do assistant.

### Seções e orçamento

| Prioridade | Seção | Conteúdo e limites padrão |
| --- | --- | --- |
| 1 | `turnos` | 6 mensagens user/assistant do chat, mais antigas primeiro; 300 caracteres por user, 700 por assistant na renderização |
| 2 | `tarefa` | Até 3 snapshots enviados pelo Harness; apenas a tarefa mais recente traz até 2 resultados bem-sucedidos, até 800 caracteres cada |
| 3 | `fatos` | Até 3 fatos globais relevantes; chave até 80 e valor até 200 caracteres |
| 4 | `memoria` | Até 3 conversas encontradas lexicalmente, excluindo conteúdos idênticos aos turnos recentes; até 400 caracteres por conteúdo |
| 5 | `estrategias` | Até 3 estratégias; objetivo até 220, até 5 passos de até 160 caracteres |
| 6 | `skills` | Contexto lexical do SkillLibrary; limite interno padrão de 3 skills e corte textual próprio |

O orçamento final padrão é **3600 caracteres**, não tokens. A montagem percorre a ordem acima, corta uma seção quando necessário e deixa de incluir seções quando restam menos de 80 caracteres. Isso pode retirar fatos/estratégias/skills mesmo que existam no banco. `ContextSnapshot.turnos` conserva os objetos recuperados; os cortes descritos são do texto renderizado.

Cada consulta auxiliar protegida captura exceções em `ContextSnapshot.erros`; o Harness as registra e pode continuar. `persiste=True` indica store configurado, não sucesso de todas as gravações.

A seção de tarefas não replica argumentos e exclui resultados da ferramenta `ler_area_transferencia_windows`. **Essa exclusão vale para essa seção**; não é garantia de que texto semelhante jamais apareça em conversas, respostas ou estratégias.

### O que segue para as rodadas do modelo

A primeira rodada recebe objetivo e contexto no estado textual. O estado é cortado em **4500 caracteres** pelo Harness. Nas continuações, [harness_round_input.py](../../core/harness_round_input.py) usa estado sem o contexto completo, até 2 entradas recentes de histórico, chamadas da resposta anterior e seus outputs; imagens podem ser adicionadas em mensagens user.

O Harness passa `response_id=None` e esforço `none`. Portanto **não usa previous_response_id**, embora o provider aceite esse argumento para outros chamadores. Limitar o estado não limita sozinho todo o payload: outputs e imagens são itens separados. O corte textual também não equivale a resumo semântico.

A docstring do helper diz preservar reasoning; o loop observado só copia itens `function_call`. Essa divergência já está registrada na Etapa 1; compatibilidade de reasoning com modelos reais continua pendente.

## 4. Persistência e recuperação

O caminho padrão de [PersistentMemoryStore](../../memory/store.py) é `data/memory/auren_memory.sqlite3`, relativo à raiz calculada pelo módulo. O construtor aceita outro path. A constante `MEMORY_DB_PATH` de config existe, mas a composição atual instancia o store sem passá-la: mudar apenas essa constante não redireciona o banco.

| Tabela | Escopo | Escrita e leitura |
| --- | --- | --- |
| `memorias` | Global ao banco | Chave única; salvar faz insert/upsert e preserva criação; consultar ranqueia chave/valor/categoria; esquecer remove chave exata |
| `conversas` | `chat_id` obrigatório na gravação | Papéis user/assistant/system; recentes incluem somente user/assistant, em ordem cronológica |
| `estrategias` | `chat_id` opcional | Objetivo, passos JSON, resultado, sucesso e datas; busca com ID filtra esse chat |

As operações usam SQL parametrizado, conexões por operação e RLock por instância. Não há criptografia aplicada por esse módulo, expiração automática ou compactação/retention de registros. A leitura de fatos carrega a tabela inteira antes de ranquear; não existe índice vetorial, embedding ou busca semântica implementada aqui.

Migração: se `estrategias` não tiver `chat_id`, a inicialização adiciona a coluna. Linhas antigas ficam NULL e não entram em buscas com ID específico; continuam acessíveis pela busca global de compatibilidade.

### Busca lexical e alcance

- O contexto seleciona até 12 termos únicos com pelo menos 3 caracteres, em ordem de aparição. Não há remoção completa de palavras comuns nem normalização geral de acentos.
- O store pontua presença por substring e ordena por relevância/recência. Conversas examinam até as últimas 300 linhas do escopo; estratégias até 200.
- Conversas têm limite de retorno entre 1 e 30, estratégias entre 1 e 20; a consulta de fatos no store aceita 1 a 50. Esses limites internos não substituem o contrato das tools.
- Estratégias são pontuadas pelo objetivo/resultado, não pelos passos. A busca não exige `sucesso=True`; o render do contexto não apresenta esse indicador.
- `ultimas_conversas` exige ID não vazio e retorna vazio sem ele. Já `buscar_conversas` e `buscar_estrategias` permitem busca global quando não recebem ID.

**Divergência reproduzida:** `SessionContextManager.build(None, objetivo)` deixa `turnos` vazio, porém `_render_memoria` passa `chat_id or None` à busca global. Conversas e estratégias de outros chats podem entrar nas respectivas seções. O teste chamado `test_sem_chat_id_nao_devolve_historico` só verifica `snapshot.turnos`, não o texto completo. Com ID explícito de outro chat, o cenário sintético permaneceu isolado. **O Harness normal garante sessão antes de build**; não foi demonstrado vazamento nesse caminho normal.

### Salvar, esquecer e escrita automática

As tools [salvar/consultar/esquecer](../../tools/memory.py) passam pelo Dispatcher; a política atual é `memory.read=AUTO` e `memory.write=CONFIRM`. O prompt exige pedido explícito para salvar/esquecer. A política é definida no [PermissionManager](../../core/permission_manager.py), não no store.

O registro interno de turnos/estratégias é persistência automática do ciclo, separado da tool de fatos. Não significa que cada turno invoque a confirmação de `memory.write`.

`esquecer_memoria_persistente` apaga **apenas a chave na tabela memorias**. Não apaga a conversa que originou o fato, estratégias, logs, traces ou dados remotos. Não descrever essa operação como esquecimento completo do usuário.

[harness_strategy.py](../../core/harness_strategy.py) agenda gravação quando há persistência e histórico de ferramentas; compacta cada resultado para 240 caracteres e captura o chat_id. Se a submissão à fila lançar exceção, tenta escrita síncrona. A fila não é durável nem realiza treinamento do modelo. Atalhos não passam por esse salvamento de estratégia do ciclo.

## 5. Privacidade, origem e limites

O store rejeita campos de conteúdo com qualquer substring de `BLOCKED_TERMS` (ex.: senha, token, api key). É filtro lexical, **não detector universal de segredos**: pode bloquear conteúdo benigno e não reconhecer segredo sem rótulo. SQL parametrizado não resolve essa classificação.

A redaction de [harness_logging.py](../../core/harness_logging.py) protege determinados campos/textos dos logs; não é uma transformação universal aplicada às gravações no store. `_registrar_turno` repassa o texto original. Não prometer que tudo ocultado num log também foi removido do SQLite.

Contexto e skills recebem rótulos de dado não confiável no texto. Isso é distinto da marca estruturada `conteudo_nao_confiavel` que arma a confirmação no Dispatcher. A reconstrução de memória não transporta automaticamente essa marca até o PermissionManager; a guarda é reiniciada por tarefa. O esquema das tabelas também não registra proveniência estruturada de tools. **É lacuna a investigar com cenário de ponta a ponta, não prova de exploração nesta auditoria.**

Os wrappers de gravação do Harness capturam exceções, mas não verificam todo retorno `{"ok": False}` do store. Recusa lexical pode não produzir MEMORY_ERROR. Uma resposta normal do assistant ou uma entrada de fila não prova que a persistência ocorreu.

## 6. Cache e métricas

Há dois mecanismos diferentes:

| Mecanismo | Comportamento observado |
| --- | --- |
| Cache local de resposta | [ResponseCache](../../agent/ari_native/response_cache.py), em RAM, LRU; defaults 50 itens e TTL de 600 s; retorna texto sem nova chamada ao provider |
| Parâmetros de prompt cache | Enviados ao serviço pelo provider; o código não garante hit nem mede a efetividade do TTL solicitado |

No orquestrador, só string não vazia, de até 700 caracteres após compactação, sem `tool_choice` explícito e sem termos de ação/estado da lista local pode consultar o cache. Só resposta textual sem function_call é armazenada. Hit retorna objeto com `output=[]`, `usage=None` e ID iniciado por `cached:`.

**Alcance real:** o estado inicial padrão montado pelo Harness contém termos como tela/janelas/atual que o filtro rejeita; continuações usam listas, também inelegíveis. A reprodução local confirmou que o estado padrão não é cacheável. O teste de cache chama o orquestrador diretamente com saudação; não demonstra economia no fluxo normal do Harness.

**Limite reproduzido em chamada direta:** a chave inclui mensagem, provider, modelo, prompt e rótulos estáticos, mas não `response_id` nem `reasoning_effort`. Duas chamadas diretas elegíveis com texto igual e IDs anteriores diferentes reutilizaram uma única resposta falsa. Não extrapolar esse caso ao Harness, que não usa previous_response_id e cujo estado padrão é inelegível. Antes de ampliar o cache, definir identidade de sessão/contexto e testes correspondentes.

[usage.py](../../core/usage.py) soma métricas após resposta do provider. Seus coeficientes fixos são usados para estimativa independentemente do modelo escolhido; **não são cotação atual nem fatura**. Os contadores são globais do processo, apesar do nome session, sem reset por chat implementado nesse módulo. Traces usam persistência separada e não alimentam automaticamente o contexto de memória.

## 7. Evidência, testes e lacunas

| Área | Testes lidos | O que efetivamente demonstram |
| --- | --- | --- |
| Contexto e continuidade | [test_session_context.py](../../tests/test_session_context.py) | Stores temporários, recência, fatos, corte, falhas auxiliares, Harness com modelo falso; teste sem ID só examina turnos |
| Escopo e migração | [test_session_isolation.py](../../tests/test_session_isolation.py) | IDs distintos, fatos globais, estratégias por chat e migração de coluna |
| Erro do provider | [test_provider_boundary.py](../../tests/test_provider_boundary.py) | Falha controlada e próxima tarefa saudável com callbacks falsos |
| Modelo | [test_model_config.py](../../tests/test_model_config.py), [test_model_override_startup.py](../../tests/test_model_override_startup.py) | Config, fachada, prompt e provider simulados com override em processo isolado; não testa API real |
| Cache | [test_ari_native_components.py](../../tests/test_ari_native_components.py) | Hit/miss e repetição direta; o teste com LRU/TTL no nome não exercita efetivamente expiração nem eviction |
| Ciclo de sessão | [test_harness_session.py](../../tests/test_harness_session.py) | Reuso, criação, limpeza e exceção de logger em callbacks |
| Gravação e fila | [test_harness_turn.py](../../tests/test_harness_turn.py), [test_harness_strategy.py](../../tests/test_harness_strategy.py) | Texto repassado, exceções, compactação, chat capturado, cancelamento e fallback |
| Payload das continuações | [test_harness_round_preparation.py](../../tests/test_harness_round_preparation.py) | Estado/outputs e partes de imagem sintéticas |
| Integração auxiliar | [test_ari_integration.py](../../tests/test_ari_integration.py) | Exemplos de busca SQLite e skills; revisado, não incluído na seleção local desta etapa |

**Execução local desta etapa:** 66 testes aprovados nos nove arquivos listados abaixo, Python 3.12/Linux do ambiente de trabalho, pytest 8.3.5 e jsonschema 4.26.0. Não é a suíte completa nem execução no notebook. A seleção exata foi:

```text
tests/test_session_context.py tests/test_session_isolation.py
tests/test_provider_boundary.py tests/test_model_config.py
tests/test_ari_native_components.py tests/test_harness_session.py
tests/test_harness_turn.py tests/test_harness_strategy.py
tests/test_harness_round_preparation.py
```

Reproduções adicionais, fora da suíte e sem alterar testes do repositório:

- Banco temporário com conversa/estratégia em chat-A: build sem ID recupera seções globais; build com chat-B não as recupera.
- **Achado histórico antes da correção:** um subprocesso com `AUREN_MODEL` diferente abortava o import de `auren` na verificação de coerência; a correção candidata elimina esse bloqueio, com teste de subprocesso dedicado em `tests/test_model_override_startup.py`.
- Provider falso: texto elegível igual com response_id diferente produz apenas uma chamada; estado padrão do Harness é rejeitado pelo cache.
- Cliente Responses falso: tools vazio, previous_response_id opcional e parallel_tool_calls=False chegam ao payload.

O CI hospedado da PR deve ser conferido pelo SHA em [AUREN_STATE.md](../../AUREN_STATE.md) e Actions. Nenhuma destas verificações demonstra qualidade de recordação, aceitação real do payload pelo serviço, latência, uso de microfone ou comportamento no Windows pessoal.

## 8. Pendências e manutenção

| Pendência | Evidência e próximo teste necessário |
| --- | --- |
| Override bloqueado na fachada e identidade fixa no prompt | Inicialização reproduzida; corrigir em PR de runtime com teste de entrada, não só config |
| Build sem ID faz busca global | Reprodução local; decidir contrato de ausência de ID e testar todas as seções |
| Cache direto ignora identidade de continuação | Reprodução com provider falso; revisar chave/elegibilidade antes de ampliar uso |
| Memória sem proveniência estruturada | Leitura do esquema/fluxo; avaliar cenário de reintrodução de conteúdo externo entre tarefas |
| Esquecimento parcial e filtro lexical | Semântica implementada; eventual retenção/eliminação completa exige escopo próprio |
| Gravações recusadas podem ficar sem diagnóstico | Retorno ok=False não inspecionado pelo wrapper; testar observabilidade |
| Restrições perdidas por cortes/continuação | Contexto inicial não é reenviado integralmente; validar tarefa longa com restrição relevante |

Ao mudar memória, preserve distinção entre fatos globais e chats, migração de bancos antigos, confirmação das tools e tratamento de conteúdo não confiável. Ao mudar provider/modelo, revise fachada, prompt, contrato de resposta, tratamento de falhas, cache e estimativa de uso. Ao mudar budgets, teste conteúdo efetivamente enviado, não apenas tamanho do banco ou existência de registros.

**Próxima área documental:** Etapa 4 — Windows, arquivos e visão. As pendências acima não autorizam implementação silenciosa durante essa próxima auditoria.


## Revisão de intenção por IA (PR #132, otimizada)

`providers/openai_provider.py::verify_intent` faz uma chamada separada ao **mesmo modelo configurado**, com `tools=[]`, formato estruturado e `store=False`; os tokens entram no contador de `core/usage.py`. Não há segunda IA nem cache de aprovação de ações. A chamada adicional é dispensada apenas para intenções simples que casem exatamente com a ferramenta e os argumentos propostos, sem outras ações ou histórico. Nos demais casos há custo e atraso adicionais por rodada com ação mutável; nenhum teste de API real foi autorizado nesta implementação. Erro de provider, resposta inválida e decisão não aprovada fazem o Harness interromper a execução da rodada. Veja `core/intent_verification.py` e `docs/architecture/01-nucleo.md`.
