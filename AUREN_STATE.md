# Auren — Estado oficial do projeto

> Fonte de verdade operacional do Auren.
> Antes de iniciar uma nova tarefa, compare este arquivo com a branch/PR, o head da main e o CI do GitHub.
> Histórico, memórias da conversa e documentos arquivados não substituem este estado.

Atualizado em: 2026-10-07

## Estado atual

- **Versão estável:** V48
- **Versão em validação:** V49
- **Modelo padrão:** `gpt-5.6-luna`
- **Branch/PR ativa:** `feat/tarefa-10a-lembretes` / PR #82
- **Head da main:** `0a8304e1b097d458511f017ca1f0d9da19d86726`
- **Head da PR #82:** `d52247afd8eaa321f8ddc35a57a89e70ea5f0881`
- **CI da Tarefa 10A:** verde no PR #82 — 476 passed, 6 skipped
- **Fase atual:** Novas capacidades — Tarefa 10A (Lembretes)

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


## Tarefa 10A — Lembretes persistentes

- [x] `criar_lembrete` registrado no registry, contrato, capability, Router, permissao e Dispatcher
- [x] `listar_lembretes` registrado no mesmo caminho oficial
- [x] `cancelar_lembrete` registrado como reversao natural da criacao
- [x] scheduler Windows baseado em Task Scheduler + XML, sem `shell=True`
- [x] comando agendado usa lista de argumentos e chama `python(w) -m tools.reminders --disparar <id>`
- [x] metadata local persistente em `%APPDATA%\\Auren\\lembretes.json`
- [x] criar = CONFIRM; listar = AUTO; cancelar = CONFIRM
- [x] IDs curtos e estaveis e nomes das tarefas derivados exclusivamente do ID validado
- [x] rollback de metadata quando a criacao do agendamento falha
- [x] runner interno limitado a `--disparar <id>`
- [x] testes com scheduler simulado cobrindo criacao, listagem, cancelamento, XML, argumentos, permissao, Router e Dispatcher
- [x] nenhuma dependencia nova adicionada
- [ ] portao final: `py -m pytest -q` verde no CI do PR #82
- [ ] runner live Windows `python testes_auren_live.py --rapido` — pendente porque este ambiente nao possui Windows; o focused-tests-windows do CI passou

### Decisoes da 10A

- O Agendador de Tarefas do Windows e a camada persistente de agendamento; o Auren nao precisa permanecer aberto para executar o runner do horario.
- A acao de criacao e persistente, portanto exige confirmacao humana.
- A listagem e somente leitura e consulta tambem a existencia da tarefa no scheduler para eliminar metadata obsoleta.
- O cancelamento remove a tarefa agendada e a metadata. Ele e a reversao natural da criacao e nao foi ligado ao `core/undo.py`, porque essa pilha nao esta presente na linha base desta tarefa.
- O XML usa `InteractiveToken` e `LeastPrivilege`; a tarefa foi desenhada para a sessao interativa do usuario, sem elevar privilegios.
- O ID do lembrete e a unica autoridade para derivar o nome da tarefa do scheduler. Metadata local nao pode escolher arbitrariamente outro nome para cancelamento.
- O runner envia notificacao por comandos do Windows sem shell e possui fallbacks locais; depois de notificar com sucesso, remove a ocorrencia unica e sua metadata.

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
- **#82** — Tarefa 10A: lembretes persistentes — open
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

A Tarefa 8 passou o portão final. A Tarefa 10A foi selecionada explicitamente como a frente atual; a Tarefa 9 continua registrada como pendência herdada, sem implementação silenciosa.

Próxima etapa, após o portão da 10A: Tarefa 10B — Pesquisa na web em modos. A execução manual do runner Browser Intelligence continua pendente da fase anterior.

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
