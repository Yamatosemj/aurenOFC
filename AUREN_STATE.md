# Auren — Estado oficial do projeto

> Fonte de verdade operacional do Auren.
> Antes de iniciar uma nova tarefa, compare este arquivo com a branch/PR, o head da main e o CI do GitHub.
> Histórico, memórias da conversa e documentos arquivados não substituem este estado.

Atualizado em: 2026-10-08

## Estado atual

- **Versão estável:** V47
- **Versão em validação:** V51
- **Modelo padrão:** `gpt-5.6-luna`
- **Branch/PR ativa:** `feat/tarefa-10c-proactive` / PR #84
- **Head da main:** `0a8304e1b097d458511f017ca1f0d9da19d86726`
- **CI da PR #84:** pytest completo, focused Linux e focused Windows verdes após correções; auditoria final em andamento
- **Fase atual:** Fechamento da Tarefa 10 — 10A + 10B + 10C

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
- [x] portao automatizado: `py -m pytest -q` verde no CI da PR #84 — 492 passed, 6 skipped
- [ ] runner live Windows `python testes_auren_live.py --rapido` — pendente porque este ambiente nao possui Windows; o focused-tests-windows do CI passou

### Decisoes da 10A

- O Agendador de Tarefas do Windows e a camada persistente de agendamento; o Auren nao precisa permanecer aberto para executar o runner do horario.
- A acao de criacao e persistente, portanto exige confirmacao humana.
- A listagem e somente leitura e consulta tambem a existencia da tarefa no scheduler para eliminar metadata obsoleta.
- O cancelamento remove a tarefa agendada e a metadata. Ele e a reversao natural da criacao e nao foi ligado ao `core/undo.py`, porque essa pilha nao esta presente na linha base desta tarefa.
- O XML usa `InteractiveToken` e `LeastPrivilege`; a tarefa foi desenhada para a sessao interativa do usuario, sem elevar privilegios.
- O ID do lembrete e a unica autoridade para derivar o nome da tarefa do scheduler. Metadata local nao pode escolher arbitrariamente outro nome para cancelamento.
- O runner envia notificacao por comandos do Windows sem shell e possui fallbacks locais; depois de notificar com sucesso, remove a ocorrencia unica e sua metadata.


## Tarefa 10B — Pesquisa web em modos

- [x] `pesquisar_web(consulta, modo)` registrado no Registry, Contrato, Capability, Router, Dispatcher e PermissionManager
- [x] modos `news`, `research`, `price` e `compare`
- [x] modo inferido pelo IntentResolver quando o TaskSpec nao informa o campo `modo`; pesquisa generica usa `research`
- [x] usa o web search hospedado do Responses API do provider, sem criar executor paralelo do Browser
- [x] Browser existente continua disponivel para tarefas interativas; o modelo recebe ambos quando a rota de pesquisa permitir escolha
- [x] retorno estruturado com URL, titulo e trecho
- [x] limite de ate 8 fontes, 600 caracteres por trecho e aproximadamente 5000 caracteres no conjunto
- [x] todo retorno e marcado como `conteudo_nao_confiavel`
- [x] resultados externos nao autorizam acoes automaticamente; prompt injection continua passando pela mesma guarda do PermissionManager
- [x] nenhuma dependencia nova
- [ ] portao final: `py -m pytest -q` verde no CI da PR #84
- [ ] `python testes_auren_live.py --rapido` apos a entrada em ambiente Windows real

### Decisoes da 10B

- A busca hospedada do provedor e usada como ferramenta de leitura; o Browser continua sendo a ferramenta para interacao com paginas.
- A escolha entre `pesquisar_web` e Browser permanece com o modelo dentro do subconjunto seguro selecionado pelo Router.
- `pesquisar_web` e AUTO porque somente consulta dados externos e nao altera o computador.
- O resultado da web e explicitamente nao confiavel mesmo quando vem do provedor, pois titulo, trecho e pagina podem conter instrucoes maliciosas.
- A ferramenta limita a quantidade e o tamanho das fontes antes de devolver o resultado ao modelo.
- O modo `research` usa contexto de busca maior; os demais usam contexto medio para controlar custo/latencia.
- O web search hospedado retorna as fontes consultadas via `include=["web_search_call.action.sources"]`.

## Tarefa 10C — Abertura proativa

- [x] resumo curto da sessão anterior usando os turnos persistidos da Tarefa 5
- [x] resumo consumido atomicamente na abertura, evitando repetição
- [x] resumo sem nova chamada ao modelo
- [x] monitoramento de tópicos desligado por padrão
- [x] tópicos persistidos separadamente da ativação global
- [x] ativação/desativação persistente
- [x] trava persistente de no máximo uma checagem por dia
- [x] controles passam pelo Registry, Contrato, Router, Dispatcher e PermissionManager
- [x] ativação e alteração de tópicos exigem CONFIRM; consulta de estado é AUTO
- [x] nenhum caminho paralelo de execução foi criado
- [x] testes de continuidade, consumo único, estado padrão, trava diária e tópicos adicionados
- [ ] portão final: `py -m pytest -q` verde no CI da PR #84
- [ ] runner live `python testes_auren_live.py --rapido` em Windows real

### Decisões da 10C

- Abertura usa somente dados persistidos do mesmo sistema de contexto da Tarefa 5; não depende de Mark-LV em runtime.
- A ideia de Mark-LV reaproveitada foi apenas o padrão de resumo curto consumível e a existência de uma trava diária para monitoramento.
- O resumo é determinístico e curto para não gastar uma chamada de modelo na inicialização.
- O monitoramento permanece opt-in e não roda quando desligado.
- O projeto atual não possui UI gráfica de configurações própria; os controles foram expostos como capacidades do Auren para que a interface atual e uma UI futura usem o mesmo caminho seguro.
- Nenhum código de Mark-LV foi copiado.


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
- **#84** — Fechamento da Tarefa 10 (10A + 10B + 10C) — open
- **#83** — Tarefa 10B: pesquisa web em modos — closed
- **#82** — Tarefa 10A: lembretes persistentes — closed
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

A Tarefa 8 passou o portão final. A Tarefa 10A, 10B e 10C já estão implementadas na PR #84; resta somente fechar o portão automatizado e validar o que for aplicável no ambiente Windows real.

Enquanto a Tarefa 10 não passar o portão final, não abrir novas frentes nem ampliar escopo.

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
