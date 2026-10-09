# Auren — Estado oficial do projeto

> Fonte de verdade operacional do Auren.
> Antes de iniciar uma nova tarefa, compare este arquivo com a branch/PR, o head da main e o CI do GitHub.
> Histórico, memórias da conversa e documentos arquivados não substituem este estado.

Atualizado em: 2026-10-09

## Estado atual

- **Versão estável:** V48
- **Modelo padrão:** `gpt-5.6-luna`
- **Branch/PR ativa:** `fix/a02-plugins-approval-before-import` / PR #100 (A02; base final: PR #81)
- **Head da main:** `db35ca8426845ac94b0198bf7ddea1864f7d638d`
- **Head da PR #81:** `20b52dbcf0cd4c2dea32a5f160ed188b3445f6e6`
- **CI da implementação da tarefa 8:** em execução no PR #81; a implementação anterior tinha 438 testes passando
- **Fase atual:** Plugin Infrastructure — Tarefa 8

### Correcao de seguranca A02 — PR #100 (nao incorporada)

- Origem: PR #81 e descendente PR #84 carregavam plugins com `habilitado: true` mesmo quando `aprovado: false`; um `import` pode executar codigo de topo antes de qualquer confirmacao de chamada.
- Correcao proposta em `core/plugin_loader.py`: importar apenas plugins com habilitacao e aprovacao explicitamente booleanas `true`; demais plugins ficam fora dos registries e do Dispatcher.
- Aprovar/revogar exige `auren.recarregar_plugins()` para aplicar entrada/saida do runtime; aprovar codigo Python nao equivale a isolar/sandboxar esse codigo.
- Os testes de regressao cobrem ausencia/malformacao de aprovacao, tipos invalidos e recarga do registry. Os testes antigos de `CONFIRM` sem aprovacao foram atualizados para o novo limite de seguranca.
- A PR #84 herda codigo anterior e precisara receber a correcao por atualizacao/rebase antes do merge. O A01 segue em PR #99 separada, sem inclusao nesta branch.
- Validacao final em GitHub CI pendente nesta nota; nao declarar concluido na main sem merge.

### O que já está concluído nesta fase

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

## Tarefa 8 — Carregador de plugins que passa pelo Dispatcher

- [x] carregador dedicado em `core/plugin_loader.py`
- [x] `TOOL` + `CAPABILITY` + handler entram nos registries oficiais
- [x] novo plugin parte de `CONFIRM`; aprovação fica em `plugins_aprovados.json`
- [x] habilitar/desabilitar sem reiniciar via recarregamento
- [x] dependências checadas com `find_spec` antes do import
- [x] plugin desativado não é importado
- [x] colisões, plugins inválidos e dependências ausentes são isolados com motivo legível
- [x] retorno de plugin marcado como conteúdo não confiável
- [x] prompt gera capacidades a partir do registry atual
- [x] template e exemplo `hora_atual`
- [x] testes específicos e extensão do caminho único
- [x] portão final: `py -m pytest -q` verde no PR #81 — 457 passed, 6 skipped

### Pendência herdada
A execução manual do runner Browser Intelligence em Windows continua pendente da fase anterior e não foi alterada silenciosamente nesta tarefa.

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
- **#81** — Tarefa 8: carregador de plugins via Dispatcher — open

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

A Tarefa 8 passou o portão final. A próxima tarefa é **9**, preservando a pendência herdada do runner Browser Intelligence.

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
