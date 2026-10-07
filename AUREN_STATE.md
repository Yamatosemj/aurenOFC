# Auren — Estado oficial do projeto

> Fonte de verdade operacional do Auren.
> Antes de iniciar uma nova tarefa, compare este arquivo com a branch/PR, o head da main e o CI do GitHub.
> Histórico, memórias da conversa e documentos arquivados não substituem este estado.

Atualizado em: 2026-10-07

## Estado atual

- **Versão estável:** V47 (V48 do undo e V49 de operações de arquivo em validação)
- **Modelo padrão:** `gpt-5.6-luna`
- **Branch/PR ativa:** `feat/file-operations-v49` / PR #78
- **Head da main:** `0a8304e1b097d458511f017ca1f0d9da19d86726`
- **Último commit da implementação da Tarefa 1:** `fe9e587e26f7e4bef75bf2c8eb4a9d02b75a0dc0`
- **Último head funcional validado:** `b72e43f3c04f6866f90340d1df2d3ec6782ab7b5`
- **Head da implementação da Tarefa 2 (em validação):** `119bf4fe01408580f15710f9cf63300f45c8c2bd`
- **Head da implementação da Tarefa 3 antes desta sincronização de estado:** `ec39b33d527d81ade64df7dc95eed0f3317a4983`; o branch/PR continua sendo a fonte do HEAD atual
- **CI da implementação mais recente em main:** pytest, focused Linux e focused Windows verdes
- **CI do PR #77:** full tests Linux/Windows, static-checks e visual interaction/Playwright verdes no merge ref `4139b0696fe1e378d80fccb8541e6232b91d01b5`
- **Baseline histórico de pytest:** **576 passed, 5 warnings**; baseline imediatamente anterior à Tarefa 3: Linux **605 passed, 6 skipped, 5 warnings** / Windows **611 passed, 5 warnings**
- **Novos testes da Tarefa 3:** **17**
- **Ferramentas no registry/contratos após a Tarefa 3:** **55** (eram 50 antes)
- **Tarefa atual:** **Tarefa 4 da sessão — política de confirmação reversível/irreversível e confirmação com timeout**
- **Portão da Tarefa 3:** pytest/runner live do Windows real continuam pendentes; a Tarefa 4 foi iniciada na branch ativa sem alterar silenciosamente a política de risco
- **Próxima tarefa:** aprovação explícita da reclassificação proposta em windows.clipboard.write e fechamento do portão da Tarefa 4
- **Fase do projeto:** Browser Intelligence

## Roadmap Mark

> O Mark-LV é referência de ideia, problema e casos-limite. Não é fonte de código para cópia. Cada implementação do Auren deve ser escrita de forma independente, usando sua arquitetura, nomes em português e `ToolResult`.

| Ordem | Tarefa | Origem no Mark-LV | Alvo principal no Auren | Estado |
|---|---|---|---|---|
| **0** | Kit de continuidade | padrão de continuidade do projeto | `docs/PROMPT_BASE.md`, `docs/NOTAS_DE_PASSAGEM.md`, `docs/REFERENCIA_MARK.md`, `AUREN_STATE.md` | **CONCLUÍDA** |
| **1** | Timeout, retry, escada de modelos e cooldown | `core/gemini.py` | `providers/model_ladder.py`, provider/config/usage/testes | **CONCLUÍDA** |
| **2** | Memória recuperável sob demanda | `main.py`, `memory/memory_manager.py` | `memory/store.py`, `tools/memory.py` | **BACKLOG / RETOMAR** |
| **3** | Undo reversível | `core/undo.py` | `core/` + ferramentas reversíveis | **EM VALIDAÇÃO** |
| **4** | Confirmação humana não-forjável | `core/confirm.py`, `ui.py` | `core/permission_manager.py`, `voice/confirmation.py` | **BACKLOG / PARCIAL** |
| **5** | Seleção de dispositivos de áudio | `core/audio_devices.py` | `voice/input.py`, `voice/tts.py` | **BACKLOG** |
| **6** | Continuidade de sessão | `main.py` | provider + Harness + memória | **BACKLOG** |
| **7** | Wake word + PTT/ack | `core/wake_word.py`, `core/hotkey.py` | camada de voz | **BACKLOG / PARCIAL** |
| **8** | Avatar + visemes/lip-sync | `core/avatar.py`, `core/viseme.py`, `ui.py` | nova camada visual | **BACKLOG** |
| **9** | Vídeo/HUD/theming | `ui.py` | nova camada visual/configuração | **BACKLOG** |
| **10** | Histórico/uso remoto/extensões | roadmap LVI+ em `readme.md` | novo transporte/módulos remotos + Harness conforme cada caso | **BACKLOG** |

A especificação detalhada de tarefas futuras permanece fora da implementação até que a tarefa correspondente seja ativada.

## Decisão de continuidade entre modelos

A documentação oficial atual da OpenAI descreve `previous_response_id` como mecanismo de continuidade multi-turno e permite informar um `model` por resposta, mas não afirma que um `previous_response_id` seja portátil quando a solicitação muda de modelo. Por isso o Auren adota uma política conservadora:

- a primeira tentativa usa `previous_response_id` somente no primeiro degrau
- ao trocar de modelo, o provider remove `previous_response_id` e envia `historico_completo`
- sem `historico_completo`, a troca falha com o erro estruturado `model_ladder_history_required`, em vez de perder contexto silenciosamente
- o fluxo atual do Harness não usa `response_id` entre rodadas

Fontes consultadas em 2026-10-07:
- https://developers.openai.com/api/reference/python/resources/responses/methods/create
- https://developers.openai.com/api/docs/guides/migrate-to-responses
- https://github.com/openai/openai-python

## Decisões da Tarefa 1

- Timeout padrão: **30 s**, configurável por `AUREN_REQUEST_TIMEOUT_S`. O SDK atual documenta **600 s** como timeout padrão.
- `max_retries`: **0**. O Auren controla fallback por degrau; o SDK não repete automaticamente uma chamada antes de o cooldown entrar em ação.
- Cooldowns: **300 s** para 429, **1800 s** para 503/504 e timeout, **21600 s** para 404.
- 400/401 não trocam de modelo.
- `AUREN_MODEL` continua sempre como primeiro degrau; `AUREN_MODEL_LADDER` apenas adiciona degraus posteriores e remove duplicatas.
- Sem `AUREN_MODEL_LADDER`, o degrau selecionado continua sendo somente `AUREN_MODEL`.
- Nenhuma dependência nova foi adicionada.

## O que já está concluído nesta fase

- [x] confirmação de voz consome o protocolo real da fila e rejeita itens stale/erro/legado
- [x] contexto de navegador propaga falhas internas sem mascarar sucesso
- [x] guard de Browser Verification só é resetado após `True` do verifier
- [x] preenchimento sensível usa evidência protegida sem expor o segredo
- [x] recuperação do navegador não reinicia a sessão por exceções transitórias
- [x] foco de aba é separado da referência interna `pagina`
- [x] busca de arquivos respeita a mesma política de caminhos e evita reparse traversal
- [x] screenshots possuem retenção e limites de armazenamento
- [x] encerramento por nome de processo evita `taskkill /IM` ambíguo
- [x] UI Automation não usa arquivo temporário de saída nem `ExecutionPolicy Bypass`
- [x] Kokoro e Parakeet possuem manifestos de integridade/revisão
- [x] navegação retorna `ToolResult` estruturado com evidência da URL final observada
- [x] rolagem aceita alvo semântico opcional e registra se o alvo foi encontrado
- [x] controles possuem impressão DOM estável para verificar efeitos que não expõem ARIA/URL
- [x] cliques de elementos não-âncora exigem confirmação quando o DOM não permite provar a ausência de comportamento JavaScript externo
- [x] contexto do navegador preserva snapshot estruturado completo das abas, incluindo URLs longas, para verificação determinística
- [x] runner live valida o bridge UIA pela arquitetura modular atual e consome retornos ToolResult sem tratar objetos estruturados como strings
- [x] schema estrito de fechar_aba exige indice e usa 0 para representar a aba ativa

### O que já está concluído nesta fase

- [x] contexto unificado do navegador via `obter_contexto_navegador`
- [x] contexto disponível no registry, contratos, facade e Dispatcher
- [x] Router inclui contexto junto do subconjunto de ferramentas do browser
- [x] conteúdo da página marcado como não confiável
- [x] tarefas browser compostas com ações relevantes exigem nova verificação antes da conclusão
- [x] verificação usa `obter_contexto_navegador` pelo fluxo normal do modelo/Dispatcher
- [x] ações browser simples preservam o comportamento anterior e não ganham uma rodada extra desnecessária
- [x] navegação e troca de aba têm verificação determinística de URL/aba ativa
- [x] abertura, troca e fechamento de abas expõem estado estruturado antes/depois e têm validação determinística de contagem e aba ativa
- [x] preenchimento de campos não sensíveis tem verificação determinística do valor observado
- [x] clique navegacional expõe evidência estruturada e pode ser verificado deterministicamente pelo destino observado
- [x] cliques sem navegação capturam sinais determinísticos de estado do controle (aria-expanded, aria-pressed, aria-selected, checked, selected, open e data-state) quando disponíveis
- [x] cliques sem navegação também capturam mudanças de visibilidade em diálogo, menu e listbox, além de popover e `details[open]`
- [x] clique sem navegação possui fallback por impressão DOM do próprio controle
- [x] leitor de página expõe esses estados para permitir comparação independente após a ação
- [x] rolagem expõe métricas estruturadas e possui verificação determinística da posição observada
- [x] runner live separado possui casos explícitos de verificação pós-ação para navegação e rolagem

### Próximo passo da fase

**Concluir a validação da verificação por tipo de ação e depois executar o runner live**, mantendo o princípio de não criar novas integrações:

- navegação: confirmar título/URL efetivos — **parcialmente concluído**; URL já é comparada de forma determinística
- abas: confirmar quantidade, aba ativa e destino — **parcialmente concluído**; abertura/troca/fechamento já carregam evidência estruturada e a contagem/aba ativa são comparadas deterministicamente
- interação com elemento: confirmar o estado relevante da página ou controle — **parcialmente concluído**; preenchimento não sensível e cliques navegacionais já têm comparação determinística, e cliques sem navegação agora verificam sinais específicos do controle ou mudanças estruturadas de dialog/menu/listbox
- rolagem: posição de rolagem já é verificada deterministicamente; confirmar automaticamente o conteúdo esperado continua como etapa posterior
- qualquer verificação continua tratando conteúdo da página como dado não confiável, nunca como instrução
- resultado `None` do verificador não encerra mais uma verificação obrigatória; somente `True` limpa a pendência

## Correções da auditoria validadas

As correções abaixo já estão implementadas no branch ativo; o CI do head validado está verde. A execução L4/L5 com modelo real continua sendo um passo manual e explícito.

- confirmação de voz usa o protocolo real `("audio", CapturedAudio)`, rejeita `("erro", exc)`, descarta áudio stale e normaliza respostas afirmativas com segurança
- contexto de Browser propaga falhas de leitura em vez de mascará-las como sucesso
- Browser Verification só limpa pendência e reinicia guard após evidência positiva `True`
- preenchimento sensível possui verificação local por compromisso HMAC sem expor o segredo
- recuperação do Browser não reinicia a sessão por exceções transitórias; recriação depende de fechamento confirmado
- foco de aba é observado independentemente da referência interna `pagina`
- back/forward/reload/keyboard possuem evidência estruturada e verificação conservadora por tipo de ação
- clique não navegacional usa estado de controle moderno, incluindo `aria-checked`, `details`, `alertdialog` e `popover`
- clique seguro exige evidência estrutural do elemento antes de receber `AUTO`
- política de conteúdo não confiável não pode elevar uma capacidade `BLOCKED` e é consumida após uma confirmação contada
- busca de arquivos compartilha a política de caminho e evita symlink/junction/reparse traversal
- raiz ampla de OneDrive deixou de ser implicitamente permitida
- leitura/inspeção rejeitam resultados quando a identidade do arquivo muda durante a operação
- hashing SHA-256 de arquivos gigantes é limitado para inspeções comuns
- Kokoro e Parakeet usam referências de artefato e verificações de integridade
- métricas ASR/TTS passaram a ser medidas no caminho real de voz

## Segurança e base estrutural concluídas

- [x] allowlist de leitura/inspeção de arquivos
- [x] defesa contra prompt injection de conteúdo não confiável
- [x] política de permissões endurecida
- [x] exceções genéricas reduzidas em caminhos críticos
- [x] dependências principais fixadas
- [x] modelo configurável por ambiente com padrão `gpt-5.6-luna`
- [x] Windows dividido por domínio
- [x] Browser dividido em leitura, elementos e navegação
- [x] Harness dividido em runtime, guards, ciclo e demais mecanismos
- [x] runner live separado da suíte pytest
- [x] trace persistente por tarefa
- [x] validação visual Windows com geometria/coordenadas protegidas

## PRs mais recentes

- **#48** — extração de Windows UI Automation — merged
- **#49** — extração de status do Windows — merged
- **#50** — extração de captura de tela — merged
- **#51** — extração de leitura do Browser — merged
- **#52** — extração de interação com elementos do Browser — merged
- **#53** — extração de navegação do Browser — merged
- **#55** — extração do runtime de sessão/logging do Harness — merged
- **#56** — extração do ciclo de execução do Harness — merged
- **#57** — separação do runner live de regressão — merged
- **#58** — Browser Context Intelligence inicial — merged
- **#60** — contexto do Browser incluído no roteamento especializado — merged
- **#61** — verificação após ações relevantes do Browser — merged
- **#64** — verificação determinística de navegação e troca de aba — merged
- **#66** — verificação determinística de preenchimento de elemento — merged
- **#69** — verificação determinística de rolagem e persistência da evidência entre rodadas — merged
- **#72** — cobertura do Browser Intelligence no runner live — merged
- **#76** — normalização CRLF — fechado sem merge; correção e regressão absorvidas pela linha do PR #77
- **#77** — refinamento da verificação por tipo de ação — aberto; inclui cliques não navegacionais

## Contratos atuais importantes

- Conteúdo vindo de páginas web é **dado não confiável**
- Conteúdo não confiável nunca autoriza uma ação por si só
- Ações continuam passando pelo Router, Dispatcher e PermissionManager normais
- Não existe caminho paralelo de execução para Browser Intelligence
- A tarefa não deve declarar sucesso quando uma verificação obrigatória ainda estiver pendente
- Mudanças de escopo devem virar backlog, não execução silenciosa

## Próximas etapas

A infraestrutura pesada desta fase está **encerrada** após a validação operacional determinística do Browser Intelligence e o CI verde no head validado.

O único passo de validação que permanece fora do CI é a bateria L4/L5 do runner live com navegador e modelo reais em Windows, mantida como execução manual porque depende do ambiente real e do provider. Isso não deve ser substituído por mocks apenas para obter CI verde.

Novas capacidades e frentes ficam fora desta etapa e permanecem no backlog.

## Registro final da Tarefa 1

- Tarefa 1 concluída e validada pelo portão de saída.
- Full pytest Linux: **589 passed, 6 skipped, 5 warnings**.
- Full pytest Windows: **595 passed, 5 warnings**.
- Static checks: verdes.
- Visual/focused CI: verde.
- Não houve alteração de Browser/Windows; o runner live manual não é requisito desta tarefa.
- Runtime permanece em **V47**.
- Próxima frente: **Tarefa 2 — memória recuperável sob demanda**.

## Registro da Tarefa 3 da sessão — Operações de arquivo seguras

Esta transição adiciona cinco ferramentas de arquivo, mantendo o fluxo único Router → Dispatcher → Contrato → Permissão → Ferramenta → ToolResult. A numeração continua separada do roadmap histórico: o roadmap interno chama o undo de Tarefa 3, enquanto esta sessão usa Tarefa 3 para operações de arquivo conforme o prompt-base recebido.

- Ferramentas: `mover_arquivo`, `copiar_arquivo`, `renomear_arquivo`, `criar_pasta` e `enviar_para_lixeira`.
- Caminhos: operações de mutação usam a mesma allowlist de `ler_arquivo`, mas endurecida para BLOQUEIO fora das raízes permitidas; symlink, junction e outros reparse points no caminho são recusados sem seguir o alvo.
- Destino: nenhum destino existente é sobrescrito; a escolha desta tarefa é retornar erro estruturado `destination_exists`, em vez de gerar `(1)`, para manter resultado previsível.
- Undo: mover, copiar, renomear e criar pasta registram reversão; mover/renomear só restauram quando o arquivo continua com o mesmo SHA-256, copiar só remove a cópia se ela continuar idêntica, e criar pasta só remove se ainda estiver vazia.
- Lixeira: `SHFileOperationW` é chamado com `FOF_ALLOWUNDO`; exclusão permanente não faz parte do runtime. A Lixeira não registra undo porque a restauração não é considerada confiável neste desenho.
- Permissões: `file.manage` = AUTO; `file.trash` = CONFIRM. Ambas contam no orçamento de ações.
- Dependências: nenhuma nova dependência foi adicionada.
- Testes: 16 testes novos; o total esperado sobe de 605 para 621 no Linux e de 611 para 627 no Windows, sujeito ao CI final.
- Runner live: ainda pendente, pois depende do Windows real do Auren e não deve ser falsificado por mocks.

## Registro da Tarefa 2 — Undo reversível

Esta transição implementa o undo solicitado pelo prompt da sessão. O roadmap interno anterior ainda numerava essa frente como Tarefa 3; a diferença de numeração fica registrada aqui para não transformar continuidade de conversa em falso histórico.

- Implementação: core/undo.py com MAX_DEPTH = 10, lock, LIFO, rótulo e horário UTC por entrada, peek, history, can_undo, clear e retenção da entrada quando a reversão falha.
- Ferramenta: desfazer_ultima_acao passa por registry → contrato → capability undo.control → PermissionManager → Dispatcher → ToolResult.
- Áudio: obter_audio_windows agora expõe percentual e mudo em data; volume e mudo capturam o estado anterior antes da alteração e registram undo somente quando esse estado foi observado com sucesso.
- Falha do undo: o callback de reversão retorna ToolResult; se falhar, desfazer_ultima_acao devolve erro estruturado e mantém a entrada no topo para nova tentativa.
- Router: pedidos como 'desfaz' entram no grupo especializado de undo sem contaminar COMMON_TOOLS.
- Dependências: nenhuma nova dependência.
- Testes: 16 novos testes de cobertura adicionados; o baseline conhecido é 576 passed.
- Validação externa: o GitHub Actions do head da implementação fechou com full pytest Linux 605 passed, 6 skipped, 5 warnings; full pytest Windows 611 passed, 5 warnings; static-checks e visual interaction verdes. O runner python testes_auren_live.py --rapido ainda não foi executado manualmente no Windows real.
- Status: a implementação está no branch ativo, mas V48 ainda não é estável enquanto o portão de saída não for fechado no ambiente apropriado.

## Backlog

A Tarefa 3 da sessão não cria novos itens fora do escopo; o próximo trabalho de confirmação humana permanece o item previsto no roadmap.

Próximas tarefas de roadmap:

- Tarefa 2 — memória recuperável sob demanda (retomar; não foi declarada concluída nesta sessão)
- Tarefa 4 — confirmação humana não-forjável
- Tarefa 5 — seleção de dispositivos de áudio
- Tarefa 6 — continuidade de sessão
- Tarefa 7 — wake word + PTT/ack
- Tarefa 8 — avatar + visemes/lip-sync
- Tarefa 9 — vídeo/HUD/theming
- Tarefa 10 — histórico/uso remoto/extensões

Ideias futuras que não fazem parte da tarefa atual:

- memória contextual/semântica mais avançada
- inteligência geral do Windows
- multi-device
- terminal no celular
- ESP32/Arduino
- Minecraft
- wake word
- interface visual avançada

## Regra de continuidade

Toda mudança relevante de arquitetura, comportamento, capacidade, versão ou próximo passo deve atualizar este arquivo na mesma transição.

Fluxo oficial:

`AUREN_STATE.md → branch/PR → CI → implementação → testes → atualização do estado`


## Registro da Tarefa 4 da sessão — Política reversível/irreversível e confirmação com timeout

Estado: **EM IMPLEMENTAÇÃO / AGUARDANDO APROVAÇÃO DA POLÍTICA**

- A auditoria confirmou que o Undo real da linha V49 existe em core/undo.py, com LIFO, limite 10 e preservação da entrada quando a reversão falha.
- Mover/copiar/renomear/criar pasta registram undo condicionado ao estado observado; volume e mudo também capturam o estado anterior antes de registrar reversão.
- memory.write permanece CONFIRM: esquecer_memoria_persistente não restaura o valor/categoria/timestamp anterior de uma atualização.
- windows.clipboard.write foi identificado como alteração atualmente não reversível pelo Auren: não há snapshot/undo do clipboard. A proposta é AUTO → CONFIRM, mas nenhuma reclassificação foi aplicada sem aprovação.
- As 28 capabilities atuais do PermissionManager foram classificadas e a matriz completa foi registrada em docs/POLITICA_DE_CONFIRMACAO.md.
- A confirmação ganhou gate de uma pendência por canal, token opaco mantido na interface, timeout padrão de 90 s, expiração como negativa e descarte de token/resposta atrasados.
- O token não faz parte de ConfirmationRequest nem dos argumentos enviados pelo modelo.
- Texto e voz continuam atrás do mesmo ConfirmationChannel; o canal de voz usa agora o timeout oficial de 90 s.
- Foi adicionada uma regressão que exige correspondência exata entre capabilities registradas e CAPABILITY_POLICY; capability nova sem nível explícito faz a suíte falhar.
- CI da implementação: static-checks e Playwright smoke verdes; full pytest Linux e Windows reproduziram as 4 falhas preexistentes da V49, enquanto os 5 testes novos desta tarefa passaram.
- Runner python testes_auren_live.py --rapido: continua pendente no Windows real porque este ambiente não é o computador do Auren.

Arquivos desta transição:
- core/confirmation.py
- voice/confirmation.py
- voice/main.py
- tests/test_confirmation.py
- tests/test_permission_policy.py
- docs/POLITICA_DE_CONFIRMACAO.md
- AUREN_STATE.md

Ficou pendente:
- Aprovar ou rejeitar explicitamente windows.clipboard.write: AUTO → CONFIRM.
- O portão final ainda não fecha porque o full pytest não está verde: Linux 624 passed, 6 skipped, 4 failed; Windows 630 passed, 4 failed. As 4 falhas são as mesmas presentes no head V49 anterior.
- Executar python testes_auren_live.py --rapido no Windows real antes de declarar o portão externo concluído.

Próxima tarefa:
- Depois da aprovação e do portão: consolidar a política no PermissionManager somente para as reclassificações aprovadas.


### Evidência CI da Tarefa 4

- Head de código validado: 8da961772abccac15ec7a6090293128469ae02aa.
- Baseline imediatamente anterior, head V49 d19ebf511d5d35623e187436c432b057a76428c5: Linux 619 passed, 6 skipped, 4 failed; Windows 625 passed, 4 failed.
- Tarefa 4: Linux 624 passed, 6 skipped, 4 failed; Windows 630 passed, 4 failed.
- Os 5 testes adicionados pela Tarefa 4 aparecem entre os testes aprovados; nenhuma falha do CI aponta para core/confirmation.py, voice/confirmation.py ou os novos testes.
- As 4 falhas reproduzidas continuam restritas à linha de operações de arquivo/roteamento da Tarefa 3:
  - test_file_operation_requests_use_specialized_route
  - test_file_operation_task_specs_resolve_to_local_capabilities
  - test_principais_ferramentas_do_registry_passam_por_contrato_permissao_e_handler
  - test_trash_shell_operation_requests_recoverable_delete
- Essas mesmas 4 falhas já estavam presentes no head V49 anterior e não foram introduzidas pela Tarefa 4.
- static-checks: verde.
- playwright-live-smoke: verde.
- Execução manual do runner live no Windows real: pendente.
