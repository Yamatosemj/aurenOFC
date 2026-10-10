# Arquitetura 05 — Navegador e Browser Intelligence

> **Etapa 5, auditoria estática:** código da `main` no commit `946f21e2b3d629ce4e8e157ded5dc97c4d1e65d4` (2026-10-10). Este documento descreve a implementação e as expectativas dos testes, **não** uma validação de navegação Live, login, sites remotos ou serviços externos.
>
> Leia também [01 — núcleo](01-nucleo.md), [02 — roteamento e segurança](02-roteamento-seguranca.md) e [04 — Windows e visão](04-windows-arquivos-visao.md). O navegador **não** é um agente separado: as ferramentas continuam passando por Router, Dispatcher, contrato, PermissionManager e ToolResult.

## 1. Responsabilidades e pontos de entrada

| Fonte | Responsabilidade concreta |
| --- | --- |
| [`tools/browser.py`](../../tools/browser.py) | Fachada, singleton de módulo Playwright/Chromium, perfil persistente, navegação e gestão de abas |
| [`tools/browser_navigation.py`](../../tools/browser_navigation.py) | Tecla na página, voltar/avançar/recarregar e rolagem com métricas |
| [`tools/browser_elements.py`](../../tools/browser_elements.py) | Localização heurística de elementos visíveis, clique, preenchimento e detecção de nova aba |
| [`tools/browser_reading.py`](../../tools/browser_reading.py) | Resumo adaptativo do DOM: textos, campos, links e cards de vídeos, com limites |
| [`tools/browser_context.py`](../../tools/browser_context.py) | `obter_contexto_navegador`: combina abas, leitura da página e estado da rolagem em `ToolResult` não confiável |
| [`core/browser_verification.py`](../../core/browser_verification.py) | Comparador determinístico entre ação anterior e contexto posterior; retorna `True`, `False` ou `None` |
| [`core/harness_heuristics.py`](../../core/harness_heuristics.py) | Detecta pedidos de navegador compostos/verificáveis e condições de conclusão local |
| [`core/harness_multitab.py`](../../core/harness_multitab.py) | Extrai destinos explícitos/serviços conhecidos em abas numeradas e compara com `listar_abas` |
| [`core/harness_tools.py`](../../core/harness_tools.py) | Marca ação relevante como pendente e processa contexto posterior, preservando estado entre rodadas |
| [`core/harness_cycle.py`](../../core/harness_cycle.py) | Habilita verificação apenas quando a heurística do objetivo exige; chama comparador |
| [`core/harness_guards.py`](../../core/harness_guards.py) | Impede conclusão com verificação pendente, tenta novamente e termina em falha após o limite |
| [`core/router.py`](../../core/router.py) | Oferece subconjunto de tools por domínio; não autoriza ações |
| [`tools/dispatcher.py`](../../tools/dispatcher.py) | Único caminho de chamada/normalização e marcação de fonte externa |
| [`core/permission_manager.py`](../../core/permission_manager.py) | Decisão AUTO/CONFIRM/BLOCKED com regras por ação e guarda de origem não confiável |

### Fluxo resumido

```text
Objetivo → Harness → Router (seleciona ferramentas)
                   → modelo/função ou atalho autorizado
                   → Dispatcher → ToolContract → PermissionManager
                   → tools/browser* → ToolResult → Harness
                                             ↓ se tarefa composta verificável
                          ação marcada como pendente
                          obter_contexto_navegador (nova tool, via Dispatcher)
                          core/browser_verification.py (compara dados)
                          True: limpa pendência; False/None: permanece pendente
                          guard: nova tentativa ou falha, nunca sucesso presumido
```

As **14 ferramentas browser** atuais no grupo `TOOL_GROUPS["browser"]` são `navegar_navegador`, `obter_contexto_navegador`, `ler_pagina`, `clicar_elemento`, `preencher_elemento`, `pressionar_tecla`, `listar_abas`, `abrir_nova_aba`, `trocar_aba`, `fechar_aba`, `voltar_pagina`, `avancar_pagina`, `recarregar_pagina` e `rolar_pagina`. O registry geral da revisão contém 49 tools. Browser Intelligence é comportamento do Harness e dessas tools, **não** um segundo executor nem uma ferramenta independente.

## 2. Sessão Playwright, navegação e abas

[`config.py`](../../config.py) define `BROWSER_PROFILE_DIR = PROJECT_ROOT / "browser_profile"`. `browser.py` inicializa `sync_playwright` e `chromium.launch_persistent_context` com o perfil local. O modo inicial é `visivel`; `oculto` ativa headless. Mudar modo, perder contexto ou falhar uma referência pode disparar reinicialização. `navegar_navegador` acrescenta `https://` quando não encontra o prefixo `http(s)://`, usa `goto(wait_until="domcontentloaded", timeout=30000)`, espera brevemente título e faz até **duas tentativas** em falhas; voltar/avançar/recarregar usam timeout de **12 s**.

`browser_context`, `pagina`, `browser` e `playwright` são variáveis globais do módulo, **não** sessões isoladas por `chat_id`. Cookies/local storage podem permanecer no perfil após reiniciar. A inspeção deste código **não comprova** isolamento entre diferentes conversas, limpeza segura dos dados nem separação de contas; também não documenta o browser como serviço remoto.

- `listar_abas` descreve abas existentes, número, título, URL e índice ativo. A lista usa as páginas abertas do contexto e o índice é **1-based**.
- `abrir_nova_aba` cria página e opcionalmente navega; se for necessário trocar modo, reinicia o contexto; há fallback que tenta recriar contexto após erro. Abrir aba sem URL é possível.
- `trocar_aba` atualiza a referência `pagina`; não é uma garantia universal de foco da janela física do sistema operacional.
- `fechar_aba` usa `close()` na página escolhida (por padrão, a atual), reatribui uma página remanescente e informa quando a última foi fechada. A política exige confirmação para fechamento.
- `obter_pagina` pode criar/recriar contexto ou nova página ao ser chamado. Portanto, até uma consulta que o chama pode **alterar o estado operacional** se não houver contexto ativo. Não descreva todo o caminho de leitura como estritamente livre de efeitos locais.

Essa API controla um Chromium do Playwright; ela **não é automação arbitrária das abas do Chrome/Edge do usuário**. Não declarar sessão compartilhada com navegadores externos nem login prévio garantido.

## 3. Leitura do DOM e contexto unificado

[`ler_pagina(foco)`](../../tools/browser_reading.py) avalia o DOM da página ativa. Pontua termos do foco, ordena controles/links/trechos e devolve um resumo, não o HTML integral nem uma extração sem perdas. Conforme o foco detectado:

| Foco heurístico | Snippets máximos | Controles/links máximos | Tamanho final de texto |
| --- | --- | --- | --- |
| Operacional (campos, botões, resultados etc.) | 7 | 10 / 10 | 2.400 caracteres, exceto faixa de resultados |
| Contextual (resumo, explicação, análise etc.) | 14 | 14 / 14 | 3.800 caracteres |
| Genérico | 10 | 12 / 12 | 2.400 caracteres |
| Pedido de resultados numerados 6+ | Conforme foco | Conforme foco | Até 5.200 caracteres |

A leitura procura elementos visíveis (inputs, textarea, select, buttons e roles), links e trechos de `document.body.innerText`. Campos detectados como senha/código/token são exibidos como `[REDACTED]` no inventário de controles; **essa heurística lexical não é sanitização completa de todo texto da página** (nem garante não capturar segredo exibido em outro lugar do DOM).

Há tratamento especial para cards de vídeos de YouTube (título, canal, duração, visualizações, URL, até dez cards estruturados, com heurísticas para ignorar anúncios e playlists). É extração baseada em seletores e texto: mudanças no site, anúncios sem marcadores reconhecidos e elementos dinâmicos podem gerar omissões ou classificações erradas; **não** é uma API oficial do YouTube nem garantia de ordenação sem erro.

**Efeito lateral importante:** quando o foco pede vários resultados, a própria `ler_pagina` pode esperar e usar `mouse.wheel` para coletar mais itens (até oito ciclos na ramificação 6+). Portanto, a ferramenta anunciada como leitura pode **rolar fisicamente a página do Chromium**. Esta diferença é observável diretamente no código e fica registrada para uma eventual tarefa de contrato/comportamento, **sem modificar runtime nesta PR**.

`obter_contexto_navegador` une `listar_abas` + `ler_pagina(foco)` e tenta coletar `scroll_y`, `scroll_height`, `viewport_height` via `evaluate`. Retorna `ToolResult.success` com `data={foco, abas, pagina, scroll}` e `conteudo_nao_confiavel=True`. Se a leitura do DOM devolve string de erro como `"Nao consegui ler a pagina..."`, o wrapper **não checa esse texto antes de retornar `ok=True`**. Essa condição merece reprodução controlada antes de alterar qualquer contrato, porque uma leitura parcial pode ser percebida como sucesso da tool de contexto.

## 4. Elementos, preenchimento, clique e rolagem

[`encontrar_elemento`](../../tools/browser_elements.py) prioriza diferentes roles acessíveis conforme o pedido: no preenchimento, `searchbox`/`textbox`/`combobox` vêm antes de botão/link. Procura atributos exatos (`id`, `name`, `aria-label`, `placeholder` em campos), depois nome acessível exato por role, nome parcial e, por último, label/placeholder/texto; filtra elementos visíveis e escolhe pelo índice. **É heurística de seleção**, não prova de identidade única ou intenção do usuário. `indice` depende da lista dinâmica.

`clicar_elemento` registra URL anterior, tag/href quando disponíveis, executa `click(timeout=10000)`, compara páginas antes/depois e adota a nova aba quando detectada. A saída textual diz `Navegacao: sim/nao` segundo alteração de URL/aba; **não comprova** que um formulário foi enviado, uma compra efetuada ou uma tarefa externa finalizada. `preencher_elemento` faz `fill(texto, timeout=10000)` e devolve mensagem textual; a checagem de valor, quando habilitada, é posterior.

[`browser_navigation.py`](../../tools/browser_navigation.py) oferece `pressionar_tecla` via teclado da página e `rolar_pagina` com `cima`, `baixo`, `inicio` ou `fim`. A rolagem devolve `ToolResult` com posição antes/depois, altura do documento e viewport. Invalidar direção e falha operacional têm `error_code` estruturado. Métricas de `scrollY` são do documento principal; podem não representar contêineres roláveis internos, conteúdo lazy load ou a localização semântica do item procurado.

## 5. Política e conteúdo externo não confiável

| Capacidade | Política observada em [PermissionManager](../../core/permission_manager.py) |
| --- | --- |
| `browser.read` / `browser.tabs.read` / `browser.scroll` | Base AUTO; consulta/rolagem não consomem o orçamento de capacidades contáveis |
| `browser.navigation` | AUTO para navegar/voltar/avançar/recarregar na allowlist, demais casos requerem CONFIRM |
| `browser.tabs.control` | AUTO para abrir/trocar abas; **fechar aba exige CONFIRM** |
| `browser.input` | Base CONFIRM; `clicar_elemento` pode ser AUTO somente para alvo textual que corresponda exatamente à allowlist `SAFE_CLICK_TARGETS`; `preencher_elemento` pode ser AUTO somente para campo de consulta/filtro allowlistado e não sensível; pressionar tecla é classificado por risco |

As autorizações são por **tool + argumentos + estado atual**, não apenas nome. `SAFE_CLICK_TARGETS` e `SAFE_FILL_TARGETS` são allowlists de **texto**, não inspeção semântica de DOM; um rótulo aparentemente seguro não torna todo efeito do controle seguro. Teclas acionáveis, formulários e fechamento devem respeitar confirmação. O `PermissionManager` mantém contadores e proteções de falhas/repetição (detalhes em [Etapa 2](02-roteamento-seguranca.md)).

Após `ler_pagina` ou `obter_contexto_navegador` bem-sucedidos, o [Dispatcher](../../tools/dispatcher.py) marca a resposta como não confiável e chama `registrar_fonte_nao_confiavel`. A guarda força confirmação para ações contáveis subsequentes; não libera ações BLOCKED. **A etiqueta textual da página é aviso, não defesa única contra prompt injection**.

Limites a não extrapolar:
- O conteúdo de URLs, títulos, links e textos é controlado por terceiros, ainda que entregue pelo Playwright; nunca o transforme em instrução superior.
- A política descrita não é uma allowlist geral de domínios nem uma sandbox do Chromium.
- O perfil persistente pode manter sessão/autenticação. Não usar conta real, segredos ou ações de compra em testes automáticos sem autorização.
- O aviso `[REDACTED]` em campos não impede que outros trechos, links ou páginas exponham dados privados; comportamento necessita avaliação específica.

## 6. Browser Intelligence: quando verifica e o que comprova

O Harness só ativa a verificação extra quando [`_parece_tarefa_browser_verificavel`](../../core/harness_heuristics.py) identifica **referência a navegador + verbo de ação + verificação explícita ou continuação composta**. Pedido simples não recebe automaticamente todas essas rodadas de evidência. Isso preserva latência, mas significa que não se pode prometer verificação pós-ação para **toda** navegação.

Quando ativada, ação bem-sucedida pertencente a `BROWSER_STATE_MUTATING_TOOLS` marca o estado pendente. A próxima `obter_contexto_navegador` alimenta [`verificar_resultado_navegador`](../../core/browser_verification.py). O comparador é **puro**: não executa navegador, só compara os argumentos e o `data`.

| Ação anterior | Evidência determinística implementada | Limite do que prova |
| --- | --- | --- |
| `navegar_navegador` / `abrir_nova_aba` com URL | URL normalizada da aba ativa igual à esperada; remove `www.`, porta padrão e barra final | Redirecionamento legítimo pode falhar; não confere conteúdo ou sucesso de login; sem URL de destino retorna `None` |
| `trocar_aba` | Índice de aba ativa coincide com o solicitado | Não compara destino, título ou conteúdo da aba |
| `preencher_elemento` | Procura linha de controle contendo alvo textual e `valor=` esperado no resumo posterior | Comparação textual, não leitura direta da identidade do controle; `[REDACTED]` retorna `None` |
| `rolar_pagina` | Posição antes/depois e `scroll_y` atual coerentes, tolerância de 8 px; início/fim conferidos | Não confirma que o **conteúdo desejado** está visível ou que o scroll ocorreu em contêiner interno |
| `clicar_elemento`, `fechar_aba`, `pressionar_tecla`, `voltar_pagina`, `avancar_pagina`, `recarregar_pagina` | Comparador retorna `None` (sem verificador específico) | Contexto existe, mas não é prova determinística da intenção final |

Retornos: `True` é confirmação de **aquela condição comparada**, `False` significa divergência observável, `None` significa não haver prova específica. Em [`harness_tools.py`](../../core/harness_tools.py), só `True` limpa pendência. Uma segunda ação bem-sucedida na mesma rodada substitui a referência anterior em `browser_verification_state`; a evidência posterior é da **última ação rastreada**, não de todas as ações acumuladas. Esse é um limite de granularidade importante para tarefas longas.

Se o modelo tentar finalizar com pendência, [`harness_guards.py`](../../core/harness_guards.py) pede `obter_contexto_navegador` por até **duas tentativas de guard**; ao esgotar, encerra com `browser_verification_missing`. Um resultado sem verificador específico pode manter a pendência até a falha: não descreva o guard como garantia de que **qualquer** ação será verificável.

### Abas numeradas: proteção complementar

[`harness_multitab.py`](../../core/harness_multitab.py) extrai apenas destinos em formatos reconhecidos: URL explícita ou `KNOWN_SERVICES` e referências ordinais (primeira, segunda etc.). O último resultado `listar_abas` é usado para comparar os destinos pedidos. O guard de abas do [Harness](../../core/harness_guards.py) pode solicitar mais rodadas, mas essa estratégia **não** garante correção para frases fora dos padrões, URLs redirecionadas, títulos ambíguos ou todas as abas de uma sessão. A verificação de abas numeradas e o comparador de ação do navegador são mecanismos **distintos**.

## 7. Evidência de teste e limitações

| Testes existentes | O que foi examinado nesta auditoria |
| --- | --- |
| [`test_browser_context.py`](../../tests/test_browser_context.py) | Contexto de abas+página+scroll, ToolResult não confiável e política após leitura |
| [`test_browser_verification.py`](../../tests/test_browser_verification.py) | URL normalizada, troca de aba, resultado genérico, rolagem e posições |
| [`test_browser_element_verification.py`](../../tests/test_browser_element_verification.py) | Preenchimento por valor visível, divergência e segredo mascarado |
| [`test_browser_verification_p0.py`](../../tests/test_browser_verification_p0.py) | Detecção sintética de nova aba após clique |
| [`test_browser_navigation_scroll.py`](../../tests/test_browser_navigation_scroll.py) | Metadados antes/depois de scroll com página falsa e falha estruturada |
| [`test_harness_tools.py`](../../tests/test_harness_tools.py), [`test_harness_guards.py`](../../tests/test_harness_guards.py) | Pendência, verificador, guarda e exaustão no ciclo; sem navegador real |
| [`test_prompt_injection.py`](../../tests/test_prompt_injection.py), [`test_permission_policy.py`](../../tests/test_permission_policy.py) | Origem externa e classificações de confirmação simuladas |
| [`test_router_tool_selection.py`](../../tests/test_router_tool_selection.py), [`test_routing_single_owner.py`](../../tests/test_routing_single_owner.py) | Conjunto de tools selecionado e caminho único de roteamento |
| [`test_browser_reading_module_boundary.py`](../../tests/test_browser_reading_module_boundary.py), [`test_browser_elements_module_boundary.py`](../../tests/test_browser_elements_module_boundary.py), [`test_browser_navigation_module_boundary.py`](../../tests/test_browser_navigation_module_boundary.py) | Separação de módulos, **não** a qualidade de leitura em páginas reais |

Esses testes foram **lidos**, não executados localmente nesta revisão. Na PR #125, o primeiro HEAD revisado `e3ac3a9e2640309a90e2f7f4473d2236fe2b29ae` passou no CI hospedado: [Linux completo](https://github.com/Yamatosemj/aurenOFC/actions/runs/38096229205) (**556 passed, 24 skipped**) e [focados Linux/Windows](https://github.com/Yamatosemj/aurenOFC/actions/runs/38096229199) (Linux **166 passed/15 skipped**, Windows **181 passed**, modo seguro **110 passed** em cada sistema). **O SHA final após registrar esta evidência deve ter checks próprios aprovados antes do merge.** Nenhum teste Playwright Live, clique em site público, login, download, API paga ou notebook do proprietário foi acionado por esta etapa.

## 8. Lacunas, sem alteração de runtime

1. **Leitura nem sempre é passiva:** `ler_pagina` pode rolar para carregar resultados, e `obter_pagina` pode criar contexto/aba. Validar contrato esperado antes de mudar permissão ou comportamento.
2. **Contexto de leitura parcialmente falho:** `obter_contexto_navegador` pode retornar `ok=True` com texto de erro originado de `ler_pagina`; reproduzir teste específico antes de propor correção.
3. **Ações sem comparador:** clique, fechar aba, tecla e histórico de navegação retornam `None` mesmo quando contexto é coletado, podendo esgotar guard em tarefa composta.
4. **Verificação é da última ação rastreada:** múltiplas ações na rodada não recebem evidência individual acumulada; testar cenários concretos antes de ampliar a lógica.
5. **Verificação de preenchimento depende de string:** identidade de controle e reatividade de interfaces podem reduzir precisão; campo protegido permanece sem comparação do valor.
6. **Perfil persistente compartilhado:** estabelecer política de sessão, retenção e limites entre chats/contas antes de qualquer promessa de isolamento.
7. **DOM variável:** anúncios e cards de vídeo podem mudar; métricas de scroll e snippets truncados não equivalem ao estado íntegro da página.
8. **Sem prova física nesta PR:** pytest com mocks não substitui fluxos reais autorizados, com site instável, popup, iframe, timeout e navegador aberto.

Os itens acima são **comportamentos ou limitações de contrato para tarefas separadas**, não bugs exploráveis automaticamente demonstrados. Não corrigir navegador, permissões, prompts nem guard dentro desta PR documental.

## 9. Checklist de manutenção futura

1. Conferir estado GitHub, inventário, regras de manutenção e [Etapa 2](02-roteamento-seguranca.md).
2. Rastrear tool do [registry](../../core/tools_registry.py) → [contrato](../../core/tool_contracts.py) → [Dispatcher](../../tools/dispatcher.py) → PermissionManager → browser handler → ToolResult → Harness.
3. Para mudar navegação/abas: verificar perfil persistente, referências globais, popups, índices e efeito de reinício do modo visível/oculto.
4. Para alterar leitor DOM: separar observação de ações locais, verificar sanitização/redaction, truncamento, estrutura e sites dinâmicos.
5. Para alterar verificação: cobrir `True/False/None`, múltiplas mutações por rodada, páginas sem contexto, redirecionamentos e retries.
6. Para testes: diferenciar simulação, CI hospedado, Windows pessoal, Playwright Live e custos/permissões; não rebaixar segurança para obter CI verde.
7. Documentar mudanças e limitações na mesma PR de código; nunca introduzir caminho paralelo de execução.

**Próxima área documental:** Etapa 6 — voz, STT e TTS. Abrir outra PR somente após encerrar esta.
