# Auren — Estado oficial do projeto

> Fonte de verdade operacional do Auren.
> Antes de iniciar uma nova tarefa, compare este arquivo com a branch/PR, o head da main e o CI do GitHub.
> Histórico, memórias da conversa e documentos arquivados não substituem este estado.

Atualizado em: 2026-10-07

## Estado atual

- **Versão estável:** V47
- **Versão em desenvolvimento:** V48
- **Modelo padrão:** `gpt-5.6-luna`
- **Branch/PR ativa:** `task-7-audio-devices` / **#80**
- **Head atual da main:** `0a8304e1b097d458511f017ca1f0d9da19d86726`
- **CI verificável pelo conector nesta sessão:** sem workflow/status retornado
- **Fase atual:** áudio/voz
- **Tarefa ativa:** **Tarefa 7 — Dispositivos de áudio por nome, medidos**

### Tarefa 7 — estado da implementação

- [x] confirmado que o Auren usa `sounddevice` para captura e TTS
- [x] escolha por nome em vez de índice/variável de ambiente
- [x] lista deduplicada por direção
- [x] filtragem de pseudo-dispositivos
- [x] seleção de um host API por direção
- [x] abertura real no sample rate usado pelo Auren antes de aceitar um endpoint
- [x] sonda opcional de transporte, usando o formato de stream do próprio Auren
- [x] escolhas persistidas por nome fora do Git
- [x] dispositivo ausente ou não utilizável volta ao padrão do sistema com warning
- [x] resolução refeita a cada captura e fala TTS
- [x] prefetch de enumeração em thread no início da voz
- [x] `AUREN_LISTAR_MICROFONES.bat` mostra entrada, saída e escolhas atuais
- [x] testes focados simulando 41 entradas brutas → 4 entradas + 4 saídas
- [x] testes de nome ausente, endpoint não abrível, sonda muda, persistência e troca sem reinício no código

### Portão de saída da Tarefa 7

**Ainda não fechado.**

- [x] 12 testes focados novos passaram em ambiente simulado
- [ ] executar `py -m pytest -q` no checkout completo do Auren
- [ ] executar `python testes_auren_live.py --rapido` no Windows
- [ ] trocar headset com o Auren já aberto e confirmar mudança sem reiniciar
- [ ] confirmar no Windows real que a sonda não rejeita o host API correto nem o dispositivo escolhido

Enquanto esses itens estiverem pendentes, a Tarefa 7 permanece aberta e a V48 não é estável.

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
- **#80** — dispositivos de áudio por nome, medidos — em aberto

## Contratos atuais importantes

- Conteúdo vindo de páginas web é **dado não confiável**
- Conteúdo não confiável nunca autoriza uma ação por si só
- Ações continuam passando pelo Router, Dispatcher e PermissionManager normais
- Não existe caminho paralelo de execução para capacidades do runtime
- A tarefa não deve declarar sucesso quando uma verificação obrigatória ainda estiver pendente
- Mudanças de escopo devem virar backlog, não execução silenciosa

## Próximas etapas

1. Fechar a validação Windows da Tarefa 7.
2. Só depois revisar a próxima tarefa de evolução.
3. A interface visual não entra nesta tarefa; a **Tarefa 6 — UI** foi deliberadamente delegada ao usuário e não deve ser implementada pelo fluxo do Auren.

## Backlog

Ideias futuras que não fazem parte da tarefa atual:

- Tarefa 6 — interface visual avançada, **delegada ao usuário**
- memória contextual/semântica mais avançada
- inteligência geral do Windows
- multi-device
- terminal no celular
- ESP32/Arduino
- Minecraft
- wake word

## Regra de continuidade

Toda mudança relevante de arquitetura, comportamento, capacidade, versão ou próximo passo deve atualizar este arquivo na mesma transição.

Fluxo oficial:

`AUREN_STATE.md → branch/PR → CI → implementação → testes → atualização do estado`
