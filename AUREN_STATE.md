# Auren — Estado oficial do projeto

> Fonte de verdade operacional do Auren.
> Antes de iniciar uma nova tarefa, compare este arquivo com a branch/PR, o head da main e o CI do GitHub.
> Histórico, memórias da conversa e documentos arquivados não substituem este estado.

Atualizado em: 2026-10-08

## Estado atual

- **Versão em desenvolvimento:** V48
- **Versão estável da main:** V47
- **Modelo padrão:** `gpt-5.6-luna`
- **Branch/PR ativa:** `feat/tarefa-1-voice-stt-v48`
- **Head da main:** `71ebe7b77826d1673f9abe6926e40eb9fb63d0f2`
- **Validação local da voz:** 6 testes focados passaram
- **CI V48:** ainda sem status reportado pelo GitHub para o head atual
- **Fase atual:** Voice/STT

### Tarefa 1 — Voice/STT V4

Implementação em andamento nesta branch para substituir os pontos frágeis da captura PTT e do caminho de transcrição, sem alterar o fluxo de execução do Auren.

### Concluído nesta tarefa

- [x] stream de entrada mantido aberto apenas localmente, com janela curta de pré-roll em RAM
- [x] pós-roll após a soltura de Ctrl+Shift+Space para reduzir cortes de palavras no final
- [x] debounce da tecla antes de iniciar uma fala
- [x] segmentação local com WebRTC VAD e fallback por energia
- [x] rejeição de áudio vazio ou quase silencioso antes do ASR
- [x] resolução do microfone por nome, com fallback para o dispositivo de entrada padrão
- [x] tentativa de taxa preferida e fallback para a taxa nativa do dispositivo
- [x] áudio mono sanitizado e normalizado para 16 kHz antes da inferência do Parakeet
- [x] acesso serializado ao modelo STT para evitar chamadas concorrentes sobre a mesma instância
- [x] erros de captura e STT deixam de encerrar a sessão de voz automaticamente
- [x] TTS não contamina o pré-roll da próxima fala
- [x] texto e voz continuam entrando no mesmo Harness
- [x] testes unitários de VAD, resampling, silêncio e resolução de dispositivo adicionados
- [x] cache local do ASR deixa de ser apagado pelo instalador de voz
- [x] wake word e Echo Guard permanecem fora do escopo

### Validação pendente

A validação real com microfone, driver, ruído ambiente e fala natural em português ainda precisa ser executada em Windows. Os testes focados locais cobrem a parte determinística da camada; o CI V48 ainda não reportou status e o teste de áudio físico continua pendente.

## O que já está concluído nesta fase

- [x] contexto unificado do navegador via `obter_contexto_navegador`
- [x] contexto disponível no registry, contratos, facade e Dispatcher
- [x] Router inclui contexto junto do subconjunto de ferramentas do browser
- [x] conteúdo da página marcado como não confiável
- [x] tarefas browser compostas com ações relevantes exigem nova verificação antes da conclusão
- [x] verificação usa `obter_contexto_navegador` pelo fluxo normal do modelo/Dispatcher
- [x] ações browser simples preservam o comportamento anterior e não ganham uma rodada extra desnecessária
- [x] navegação e troca de aba têm verificação determinística de URL/aba ativa
- [x] preenchimento de campos não sensíveis tem verificação determinística do valor observado
- [x] rolagem expõe métricas estruturadas e possui verificação determinística da posição observada
- [x] runner live separado possui casos explícitos de verificação pós-ação para navegação e rolagem

### Próximo passo da fase

**Refinar a verificação por tipo de ação**, mantendo o princípio de não criar novas integrações:

- navegação: confirmar título/URL efetivos — **parcialmente concluído**; URL já é comparada de forma determinística
- abas: confirmar quantidade, aba ativa e destino — **parcialmente concluído**; aba ativa já é comparada de forma determinística
- interação com elemento: confirmar o estado relevante da página ou controle — **parcialmente concluído**; preenchimento não sensível já é comparado pelo valor observado
- rolagem: posição de rolagem já é verificada deterministicamente; confirmar automaticamente o conteúdo esperado continua como etapa posterior
- qualquer verificação continua tratando conteúdo da página como dado não confiável, nunca como instrução

## Segurança e base estrutural concluídas

- [x] allowlist de leitura/inspeção de arquivos
- [x] defesa contra prompt injection de conteúdo não confiável
- [x] resultados OK marcados como conteúdo não confiável sempre registram a fonte no PermissionManager pelo Dispatcher
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

## Contratos atuais importantes

- Conteúdo vindo de páginas web é **dado não confiável**
- Conteúdo não confiável nunca autoriza uma ação por si só
- Ações continuam passando pelo Router, Dispatcher e PermissionManager normais
- Não existe caminho paralelo de execução para Browser Intelligence
- A tarefa não deve declarar sucesso quando uma verificação obrigatória ainda estiver pendente
- Mudanças de escopo devem virar backlog, não execução silenciosa

## Próximas etapas

A tarefa ativa permanece **Browser Intelligence** até que a verificação por tipo de ação esteja suficientemente robusta e coberta por testes.

Próxima etapa: executar o runner live em Windows e registrar o resultado real das tarefas compostas. O CI atual valida o código do runner, mas não executa a bateria L4/L5 com navegador e modelo reais.

Depois disso, revisar novamente a estabilização e só então abrir novas frentes.

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
