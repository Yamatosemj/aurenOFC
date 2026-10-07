# Auren — Estado oficial do projeto

> Fonte de verdade operacional do Auren.
> Antes de iniciar uma nova tarefa, compare este arquivo com a branch/PR, o head da main e o CI do GitHub.
> Histórico, memórias da conversa e documentos arquivados não substituem este estado.

Atualizado em: 2026-10-07

## Estado atual

- **Versão estável:** V47
- **Modelo padrão:** `gpt-5.6-luna`
- **Branch/PR ativa:** `fix/browser-click-new-tab-page` / PR #77
- **Head da main:** `0a8304e1b097d458511f017ca1f0d9da19d86726`
- **Head da branch ativa:** HEAD de PR #77 (`fix/browser-click-new-tab-page`)
- **Último head funcional validado:** `b72e43f3c04f6866f90340d1df2d3ec6782ab7b5`
- **CI da implementação mais recente em main:** pytest, focused Linux e focused Windows verdes
- **CI do PR #77:** full tests Linux/Windows, static-checks e visual interaction/Playwright verdes no head validado `b72e43f3c04f6866f90340d1df2d3ec6782ab7b5`
- **Fase atual:** Browser Intelligence

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

## Backlog

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
