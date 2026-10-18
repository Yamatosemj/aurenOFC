# Arquitetura 02 — Roteamento, contratos, permissões e execução de ferramentas

Reconciliação da Fase 0: `caminho_explicito_programa`, em `core/utils.py`, identifica caminhos sem consultar o disco e é compartilhado por PermissionManager e executor. Caminhos absolutos, UNC, relativos com separador e relativos a uma unidade exigem confirmação; aspas externas correspondentes são removidas para identificar o mesmo alvo. O executor mantém a validação de `.exe` existente, o ToolResult com PID e a distinção entre inicialização solicitada e janela pronta. A confirmação acontece no Dispatcher antes do handler. Não há nova rota de execução ou aprovação automática.

> **Auditoria estática da Etapa 2** — código da main em 2026-10-10, base `b306005bafefadee84a5d90ccb7ff62727ff85d8`. Conferimos implementação, entradas do runtime e testes. **Auditado estaticamente** não significa testado com aplicativos, navegador, microfone ou ações reais. Para execução de tarefas e estados, veja [01-nucleo.md](01-nucleo.md).
>
> **Regra central:** o Router determina **quais capacidades oferecer** (e se há um atalho determinístico). **Não autoriza** operações. Toda ferramenta executável percorre o Dispatcher e a política fora do modelo, inclusive quando chamada por fast path. Os detalhes normativos continuam no **código**, não nesta cópia descritiva.

## 1. Fontes de verdade e responsabilidades

| Área | Fonte de verdade | Responsabilidade e fronteira |
| --- | --- | --- |
| Decisão local e domínios | [core/router.py](../../core/router.py), [core/local_decision.py](../../core/local_decision.py) | Detecta atalhos restritos e escolhe subconjunto de ferramentas para o modelo. **Não concede permissão.** |
| Executor de atalhos | [tools/fast_paths.py](../../tools/fast_paths.py) | Transforma decisão em chamadas de tool com formato de função; chama o mesmo executor injetado que o modelo. **Não acessa diretamente** Windows/browser. |
| Composição do runtime | [auren.py](../../auren.py), [core/response.py](../../core/response.py), [core/orchestrator.py](../../core/orchestrator.py) | Configura Harness, callbacks e Router único; orquestrador escolhe toolset com Router e chama provider. |
| Registry de funções | [core/tools_registry.py](../../core/tools_registry.py) | **Fonte dos nomes e schemas** expostos ao modelo; levantamento desta auditoria: **49 entradas**. Recontar após mudanças. |
| Validação de contrato e mapa de capacidades | [core/tool_contracts.py](../../core/tool_contracts.py) | Transforma schemas em ToolContract, confere argumentos e resolve uma capacidade como `browser.input` ou `windows.input`. |
| Dispatcher e handlers | [tools/dispatcher.py](../../tools/dispatcher.py) | **Fronteira única de execução**: decodificação, contrato, preflight, autorização, handler, resultado e marcação de conteúdo externo. |
| Política e confirmação | [core/permission_manager.py](../../core/permission_manager.py), [core/confirmation.py](../../core/confirmation.py) | Classifica risco pela capacidade e pelos argumentos. Decide `AUTO`, `CONFIRM`, `BLOCKED`, mantém orçamentos/guards e solicita decisão ao canal. |
| Resultado | [core/tool_result.py](../../core/tool_result.py) | `ToolResult.ok` é sinal estruturado de êxito/falha; ponte `from_legacy` adapta ferramentas antigas. |
| Ferramentas reais | [tools/](../../tools/__init__.py) | Executores de Windows, arquivos, navegador, memória e aplicativos. A segurança específica do seu domínio requer auditorias próprias. |

### Diagrama do percurso

~~~mermaid
flowchart TD
    A["Mensagem / Harness"] --> B{"Router: atalho local?"}
    B -->|sim| C["tools.fast_paths: cria function call"]
    B -->|não| D["core.AurenOrchestrator"]
    D --> E["Router.select_tools: subconjunto ou registry inteiro"]
    E --> F["Provider: resposta / function_call"]
    C --> G["Executor injetado"]
    F --> G
    G --> H["tools.dispatcher.executar_ferramenta"]
    H --> I["Parse JSON -> handler conhecido -> contrato"]
    I --> J["Preflight visual/UIA, quando aplicável"]
    J --> K["PermissionManager.autorizar"]
    K -->|BLOCKED / usuário nega| L["ToolResult.failure"]
    K -->|AUTO / usuário confirma| M["Handler real"]
    M --> N["from_legacy / ToolResult"]
    N --> O["Marcação de conteúdo não confiável e registro do resultado"]
    O --> P["ToolResult -> Harness / modelo"]
    L --> P
~~~

O diagrama resume **chamadas de ferramentas**; consultas ao modelo, registro da tarefa e guards de conclusão pertencem ao [ciclo do Harness](01-nucleo.md). Pré-processamento visual e preflight UIA acontecem **antes** da autorização: são passos de inspeção/transformação, não uma autorização para executar o efeito final.

## 2. Duas rotas, um Dispatcher

### Fast path determinístico

- [Router.decidir_local](../../core/router.py) delega ao `LocalDecisionEngine.choice` e **não chama API nem executa ferramenta**.
- Escolhas atualmente **executadas localmente**: `get_system_status`, `open_tabs`, `open_url`, `open_known_site`. Consulte `ESCOLHAS_EXECUTADAS_LOCALMENTE` antes de acrescentar atalhos.
- As escolhas `control_media`, `set_volume`, `set_mute` podem ser **identificadas** localmente, mas **não são executadas como fast path** na rota principal: seguem ao modelo. Não confundir reconhecimento com implementação de atalho.
- [tools/fast_paths.py](../../tools/fast_paths.py) cria um objeto com `name`, `arguments` em JSON e `call_id`, passando ao callback de execução fornecido por [auren.criar_harness](../../auren.py). Cada aba solicitada produz uma chamada individual; interrompe na primeira falha.
- A resposta compacta do fast path preserva **compatibilidade textual** com o [harness_fast_path.py](../../core/harness_fast_path.py). O ciclo de tools vindas do modelo usa `ToolResult.ok` como critério principal de resultado. Essa distinção é importante para futuras migrações.

### Seleção de ferramentas para o modelo

- [Router.select_tool_names](../../core/router.py) avalia expressões por domínio, inclui ferramentas comuns e, em casos específicos, combina domínios (por exemplo, visão + entrada/UIA, aplicativo + janela).
- Ambiguidade ou ausência de domínio claro produz **fallback ao registro completo**; o Router não é barreira de segurança, é otimização de contexto/seleção. Um subconjunto também **não significa autorização prévia**.
- Spotify desktop tem conjunto especializado, evitando carregar tools de browser apenas porque a palavra Spotify apareceu; conferir os detalhes por padrão.
- [core.AurenOrchestrator](../../core/orchestrator.py) chama `Router.select_tools` e entrega a lista ao provider. A decisão do modelo sobre uma função pode falhar/ser ambígua; o Dispatcher ainda precisa validar tudo.
- [Router.route_task_spec](../../core/router.py), `CapabilityResolver`, `TaskSpec` e `IntentResolver` **existem**, mas **não substituem o fluxo de produção**. A execução local de capability áudio está sujeita à flag `AUREN_EXPERIMENT_CAPABILITY_AUDIO` em [capability_audio_runtime.py](../../core/capability_audio_runtime.py); mesmo ali é injetado o executor normal. Ver [test_routing_single_owner.py](../../tests/test_routing_single_owner.py).

## 3. Registro, contrato e validação real

Em [tools_registry.py](../../core/tools_registry.py), cada tool define `type=function`, `name`, `description`, `parameters` e `strict`. A tabela de [TOOL_HANDLERS](../../tools/dispatcher.py) liga esses nomes a executores; `validar_registry_handlers()` compara os nomes do registry e dos handlers.

O [ToolContractRegistry](../../core/tool_contracts.py) reusa os schemas da lista, associa a categoria de capacidade e chama `ToolContract.validate_arguments()` **antes de permitir a execução**. A implementação local valida:

- argumento principal deve ser **objeto/dict** JSON; rejeita JSON inválido;
- **campos obrigatórios** declarados em `required`;
- **campos extras/desconhecidos** fora de `properties` (rejeitados pelo validador);
- tipos simples: string, integer, number, boolean, object, array e null;
- valores `enum`; `minimum` e `maximum` para números.

**Limitação importante:** este validador local **não é um motor integral de JSON Schema**. Não interpreta genericamente validação de propriedades aninhadas, `pattern`, `minLength`, `maxLength`, `oneOf`, `allOf`, `format` etc. Também usa fallback permissivo para um tipo não reconhecido. Isso **não prova** falha explorável nos schemas atuais; ao adicionar schema complexo, exigir implementação/testes correspondentes ou validador adequado.

- A categoria de uma ferramenta vem do mapa `_CAPABILITY_RULES` do contrato (p.ex. `memory.write`, `browser.input`, `windows.window.control`). Nome sem mapeamento cai em categoria `generic`, que não está autorizada pela política padrão: **falha fechada**, até revisão explícita.
- `ToolContractRegistry.validate_registry()` confere quantidade, nomes e tipo de schema raiz; não prova semântica integral de cada handler.
- Evite duplicar schemas ou uma segunda tabela de comandos em `AGENTS.md` ou aqui. A documentação deve apontar para registry + contrato + testes.

### Como adicionar uma ferramenta sem criar caminho paralelo

1. Revisar se há capacidade/handler equivalente; adicionar à lista de [tools_registry.py](../../core/tools_registry.py) só quando necessária.
2. Declarar schema **compatível com a validação efetivamente implementada** e testes positivos/negativos.
3. Registrar capacidade canônica em [tool_contracts.py](../../core/tool_contracts.py); definir e justificar nível/política em [permission_manager.py](../../core/permission_manager.py).
4. Implementar o handler em [dispatcher.py](../../tools/dispatcher.py) sem expor atalho de execução à GUI/voz/LLM fora dele.
5. Produzir [ToolResult](../../core/tool_result.py) explícito, preservando rastreabilidade e marca de fonte não confiável quando aplicável.
6. Testar sucesso, argumento inválido, permissão negada, confirmação, falha e interação com orçamento/guards. Atualizar [Router](../../core/router.py) somente se precisa ser exposta no subconjunto especializado; **falta de rota especializada não é autorização para pular política**.

## 4. Passos efetivos do Dispatcher e falhas

A ordem de [executar_ferramenta](../../tools/dispatcher.py) é observada diretamente:

1. Ler `item.name`; `json.loads(item.arguments)` deve produzir um objeto. Falhas devolvem `invalid_json_arguments` ou `invalid_arguments`.
2. Rejeitar nomes ausentes de `TOOL_HANDLERS` (`unknown_tool`).
3. Validar contrato com `validate_tool_arguments`; rejeição (`contract_error`) impede handler.
4. Para clique/arraste de mouse Windows, transformar e verificar coordenadas de visão; rejeição (`vision_coordinate_rejected`) impede ação.
5. Para `preencher_elemento_windows`, fazer **preflight UI Automation** de alvo e proteção de campo; falha (`uia_preflight_failed`) impede execução. Campos protegidos usam identidade resolvida para o preenchimento.
6. Passar `argumentos_execucao` e contexto para `PermissionManager.autorizar`. Se negado, devolver `permission_denied` sem chamar handler.
7. Para inspeção/leitura de arquivos, transportar caminho e identidade capturados pelo PermissionManager **antes** da confirmação; rejeitar mudança de destino e conferir a identidade de cada arquivo aberto antes de ler conteúdo (P0/AUD-001). Executar `TOOL_HANDLERS[nome]` sem criar uma nova aprovação após a pergunta.
8. Exceções **operacionais específicas** (`OSError`, `RuntimeError`, `TypeError`, `ValueError`, `KeyError`) convertem-se em ToolResult.failure `exception`. Outras exceções de programação podem **propagar**, em vez de serem silenciosamente interpretadas como sucesso.
9. Adaptar retorno com `from_legacy`. Em leitura bem-sucedida de `ler_pagina`, `ler_arquivo` ou `obter_contexto_navegador`, marcar `conteudo_nao_confiavel=True` e armar a política de origem, **inclusive se o resultado já veio marcado**. Preservar metadados de transformação de visão.
10. Registrar êxito/falha no gerenciador de permissões (guard/contadores aplicáveis) e devolver o `ToolResult` ao Harness.

**Importante:** chamadas inválidas rejeitadas antes de `autorizar` não consomem necessariamente o orçamento de `actions_attempted`; o Dispatcher registra sua falha por capacidade, e o PermissionManager só conta categorias configuradas. Não presumir que todos os erros têm exatamente o mesmo efeito de orçamento.

## 5. Modelo de risco e confirmação

A fonte de verdade é [PermissionManager](../../core/permission_manager.py), não os rótulos do Router.

| Nível | Comportamento |
| --- | --- |
| `AUTO` | Permissão automática para aquela **ação concreta**, segundo capacidade e argumentos. Não significa universalmente “inofensivo”. |
| `CONFIRM` | Requer aprovação do canal de confirmação injetado; em caso de negativa, o handler não executa. |
| `BLOCKED` | Bloqueio sem opção de rebaixar para confirmação; também prevalece sobre o guard de conteúdo externo. |

A política começa em `CAPABILITY_POLICY` (por capacidade) e é refinada por `nivel_da_acao`. Exemplos observados:

- **Memória:** leitura AUTO; gravação e esquecimento CONFIRM.
- **Arquivos:** busca AUTO; `file.read`/`file.inspect` passam também por política do **caminho** (permitido, exige confirmação ou bloqueado). A segurança de allowlist, symlinks e pastas protegidas pertence à auditoria de arquivos da Etapa 4.
- **Processos:** listar AUTO, encerrar CONFIRM. **Candidata do achado 9:** além da confirmação, o executor recusa a mesma lista centralizada de processos do sistema para `/IM`, `/PID` normal e `/F` e rejeita inconsistência entre nome informado e identidade verificada do PID. A decisão de confirmação não substitui as guardas do executor; `taskkill` com retorno 0 não comprova saída.
- **Windows:** leitura/status/captura AUTO; mover/focar/minimizar/maximizar/restaurar janela AUTO, **fechar janela** CONFIRM; mouse mover AUTO, clicar/arrastar CONFIRM; teclas explicitamente seguras AUTO e teclas potencialmente acionáveis CONFIRM.
- **UI Automation:** inspeção AUTO; clicar/alternar/selecionar CONFIRM; preenchimento apenas em alvo de pesquisa/filtro reconhecido pode ser AUTO, após preflight; campos protegidos ou suspeitos CONFIRM.
- **Navegador:** navegação e troca/abertura de abas AUTO; fechamento de aba CONFIRM; leitura AUTO; cliques em alvos de allowlist textual **exata** podem ser AUTO, outros CONFIRM; preenchimento de busca/filtro AUTO quando reconhecido, outros CONFIRM.
- **Áudio:** leitura e ajustes locais de volume/mudo/mídia são AUTO conforme política atual.
- **Aplicativos:** abertura comum AUTO; nomes administrativos/intérpretes (PowerShell/cmd/terminal/registro etc.) elevam a CONFIRM.

Não transforme esta lista em nova política. A enumeração exata de alvos, teclas e nomes está em `SAFE_KEYS`, `RISKY_KEYS`, `SAFE_CLICK_TARGETS`, `SAFE_FILL_TARGETS`, allowlists de ferramentas e classificadores de [permission_manager.py](../../core/permission_manager.py).

### Canais de confirmação

- [ConfirmationRequest](../../core/confirmation.py) inclui ferramenta, descrição, razão, tentativas e saldo.
- [TextConfirmationChannel](../../core/confirmation.py) pergunta `s/n`; **em `AUREN_TEST_MODE=1` nega automaticamente a confirmação interativa** para não consumir comandos de testes como aprovação.
- Canais GUI/voz podem ser injetados por `auren.criar_harness(confirmation_channel=...)`; confira implementação e testes do canal antes de prometer timeout ou UX. **A flag de teste do canal textual não é uma sandbox universal para qualquer confirmação artificial injetada.**
- As descrições de confirmação mascaram valores de campos e chaves sensíveis conforme métodos locais; confirme o que efetivamente é mascarado antes de acrescentar parâmetros privados.

## 6. Orçamento, anti-loop e origem não confiável

AUD-013 (correção candidata): a trava de falhas iguais compara a assinatura da ação solicitada com a que falhou. Uma alternativa não é recusada por esse contador sozinho; continuam valendo três falhas consecutivas, orçamento total, política e confirmação de cada ação.

| Guarda / contador | Regra efetiva |
| --- | --- |
| `max_actions=10` | Limite padrão **por tarefa** sobre tentativas das capacidades em `COUNTED_CAPABILITIES`. A verificação ocorre antes da autorização; uma tentativa contável negada também pode consumir orçamento. |
| `max_consecutive_failures=3` | Após falhas consecutivas em ações **contáveis**, recusa novas ações contáveis. Leitura não é contabilizada da mesma forma. |
| `max_same_failed_actions=2` | Repetição da mesma ação/argumentos com falha é impedida; identidade usa hash SHA-256 dos argumentos serializados, não armazenamento do segredo em claro no guard. |
| `max_no_progress_repeats=3` | Guarda de êxitos repetidos aplica-se explicitamente ao subconjunto `NO_PROGRESS_GUARD_TOOLS` (hoje `navegar_navegador`), **não a qualquer clique**. |
| `iniciar_tarefa()` | Reinicia orçamento, repetição e marcador de fonte externa; não constitui isolamento de sistema operacional. |

### Conteúdo externo e prompt injection

Uma chamada bem-sucedida de `ler_pagina`, `ler_arquivo` ou `obter_contexto_navegador` marca origem não confiável no ToolResult **e** chama `registrar_fonte_nao_confiavel`. O PermissionManager promove a `CONFIRM` ações subsequentes de capacidades **contáveis** enquanto a origem estiver pendente. Ações BLOCKED continuam bloqueadas. **Outra leitura** ainda pode ser AUTO.

**Nuance verificada:** a marca de origem é **mantida até `iniciar_tarefa()` ou novo registro/reset da tarefa**, e não apagada automaticamente após a primeira confirmação no código observado. Portanto a mensagem da docstring “próxima ação” não é uma promessa de que somente uma ação exigirá confirmação. Isso é uma postura conservadora; não foi classificado como bug.

Essa proteção **não torna todo texto remoto seguro**. Ela depende da origem ter sido classificada, de toda execução com efeitos passar pelo Dispatcher e da autorização humana ocorrer no canal correto. Nunca transformar páginas ou documentos em instruções privilegiadas do usuário.

## 7. Resultado estruturado e compatibilidade

`ToolResult` em [core/tool_result.py](../../core/tool_result.py) contém `ok`, `message`, `data`, `error_code`, `tool_name` e `conteudo_nao_confiavel`. O Harness deve usar `ok` em vez de inferir sucesso da linguagem natural.

- `ToolResult.success/failure` são preferíveis para implementações novas.
- `from_legacy` aceita ToolResult, dicionários com `ok` booleano, outros dicionários e strings legadas. Para strings, há uma **lista de prefixos de falha**, que é compatibilidade limitada e não prova sucesso real.
- **Candidata de correcao do achado 2 (auditoria 15/10):** `tools/windows_processes.py` deixa de emitir texto solto tanto em `listar_processos_windows` quanto `encerrar_processo_windows`; usa `ToolResult.failure` para erros de plataforma, argumentos, identidade/protecao do alvo, codigo de saida de `tasklist`/`taskkill` e excecoes, e `ToolResult.success` para leituras/pedidos realizados. O Dispatcher e os guards leem `ok` explicito, independentemente do idioma da mensagem. O retorno `data.encerramento_comprovado=False` permanece, mesmo quando `taskkill` devolve codigo 0. **Outras ferramentas ainda retornam strings** e nao foram migradas nesta PR; nao tratar como mitigacao global de falsos sucessos.
- `for_model()` pode devolver mensagem direta para um resultado simples ou JSON compacto com estado, erro, dados e marca de desconfiança.
- Metadados de visão `vision_coordinate_transform` são adicionados sem apagar a marca de conteúdo não confiável.

## 8. Matriz de evidências e testes

| Contrato | Testes revisados | Limite da evidência |
| --- | --- | --- |
| Router, domínios, rotas compostas, fallback amplo | [test_router_tool_selection.py](../../tests/test_router_tool_selection.py), [test_router_baseline_matrix.py](../../tests/test_router_baseline_matrix.py) | Frases de entrada e toolsets em memória; não prova qualidade de decisões reais do modelo |
| Dono único, atalhos e flag experimental | [test_routing_single_owner.py](../../tests/test_routing_single_owner.py) | Stubs de ferramentas e inspeção AST; não executa aplicativos |
| Registry, schemas, handlers, entradas rejeitadas | [test_tool_contracts.py](../../tests/test_tool_contracts.py), [test_dispatcher_contracts.py](../../tests/test_dispatcher_contracts.py) | Confere shape e samples do registry atual; não garante todas as regras JSON Schema |
| Dispatcher, erros, permissões e caminho de fast path | [test_execution_single_path.py](../../tests/test_execution_single_path.py), [test_p0_3_dispatcher.py](../../tests/test_p0_3_dispatcher.py) | Handlers simulados; preflight UIA real fica fora de alguns casos |
| Níveis e allowlists por ação | [test_permission_policy.py](../../tests/test_permission_policy.py) | Exemplos discretos; não enumera todos os estados possíveis do Windows |
| Confirmações textuais e voz | [test_confirmation.py](../../tests/test_confirmation.py) | Entradas e filas simuladas; não comprova hardware de microfone/voz |
| Conteúdo não confiável, fonte pré-marcada, bloqueio | [test_prompt_injection.py](../../tests/test_prompt_injection.py) | Simula páginas e retornos, inclusive resultado já marcado; não é prova formal anti-injeção |
| ToolResult, fallbacks legados | [test_tool_result.py](../../tests/test_tool_result.py) | Serialização e resultado estruturado |
| Relação com núcleo/Harness | [test_harness_tools.py](../../tests/test_harness_tools.py), [test_harness_loop_owner.py](../../tests/test_harness_loop_owner.py) | Conclusão/guard baseado em resultado simulado |

O **CI exato desta PR** (jobs, SHA e contagens) deve ser registrado em [AUREN_STATE.md](../../AUREN_STATE.md) após os resultados. Para documentação pura, o pytest **hospedado no GitHub** é suficiente; não rodar Live, voz, navegador, API ou notebook do proprietário sem necessidade.

## 9. Observações para acompanhamento, sem refatoração nesta etapa

Estas notas são **limitações e questões identificadas na leitura do código**. Não são automaticamente falhas reproduzidas nem autorização para correções fora de escopo.

1. **Profundidade do contrato:** `ToolContract.validate_arguments` implementa subconjunto de validação. Antes de aceitar novos schemas complexos, criar casos negativos específicos e decidir se será necessário validador completo.
2. **Marcador externo persistente:** `_fonte_nao_confiavel_pendente` não é consumida após autorização, apesar da descrição “próxima ação”. Documentar intenção e testar política desejada antes de alterar.
3. **Fast path e retorno legado:** o caminho rápido ainda classifica êxito por texto adaptado em parte do Harness, enquanto chamadas de modelo usam `ToolResult.ok`. Uma migração futura deve preservar semântica e não reduzir a segurança.
4. **Classificadores por alvo textual:** SAFE_CLICK_TARGETS e SAFE_FILL_TARGETS baseiam-se em nomes reconhecidos; o risco real de um elemento também depende da página/janela. Não supor segurança universal a partir do nome “Pesquisar”.
5. **Guard de não progresso seletivo:** repetição de `navegar_navegador` tem regra própria; outras ações obedecem orçamento e guards de falhas, mas não passam necessariamente pelo mesmo detector.
6. **UIA e coordenadas:** preflight e transformação aparecem neste fluxo, porém a prova de integridade de alvos e DPI será avaliada na auditoria de Windows/visão (Etapa 4).
7. **Execução experimental:** `CapabilityResolver/TaskSpec` atrás de flag de áudio não pode ser documentado como segundo Router de produção.

### Próxima alteração do subsistema: checklist mínimo

- Ler a chamada real desde [auren.criar_harness](../../auren.py) até [dispatcher.py](../../tools/dispatcher.py) e seus testes, inclusive fast path.
- Não confundir seleção pelo Router com autorização; preservar **contrato → permissão → handler → ToolResult**.
- Conferir se nova tool está no registry, mapa de capacidade, policy, handlers e testes; caminho desconhecido deve falhar fechado.
- Definir tipo de risco e tratamento de dados externos antes de usar AUTO.
- Preservar contadores, confirmação por canal, rejeição no modo seguro de teste e conteúdo não confiável.
- Atualizar documentação relevante e anexar resultado de pytest/CI no SHA concreto. Qualquer teste Live, execução no Windows pessoal ou ação real precisa de autorização específica.

**Estado desta auditoria:** mapa de responsabilidades e comportamento documentado **estaticamente** com testes revisados. A validação de efeitos reais fica para etapas e ambientes apropriados; nenhum arquivo de produção foi alterado.
