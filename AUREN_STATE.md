# Auren — Estado oficial do projeto

> Fonte de verdade operacional do Auren.
> Antes de iniciar uma nova tarefa, compare este arquivo com a branch/PR, o head da main e o CI do GitHub.
> Histórico, memórias da conversa e documentos arquivados não substituem este estado.

Atualizado em: 2026-10-10

## Estado atual

- **Versão estável:** V47
- **Modelo padrão:** `gpt-5.6-luna`
- **Branch/PR ativa:** `feat/remote-tests-via-chat-comment` — disparo de pytest Windows por comentario autenticado em PR; aguardando CI e aprovacao pontual da politica local do runner
- **Head da main:** consultar GitHub antes de cada tarefa; ultimo merge de codigo confirmado: PR #110 (`e6f7f0de6d4296a5e55a05c107d97b545d6dc482`)
- **CI:** PR #110: suite completa Linux 507 passed/15 skipped, testes focados Linux 139 passed/6 skipped e Windows 145 passed. Movimentacao dos launchers ainda necessita de exercicio manual por duplo clique no Windows.
- **Fase atual:** concluir testes reais no Windows via comando do chat; GUI MVP foi entregue e seu uso real foi confirmado pelo usuario, mas entrada textual precisa de melhoria posterior

### Testes Windows solicitados diretamente pelo chat (em preparacao, 2026-10-10)

- Nova workflow `.github/workflows/auren-chat-tests.yml` responde somente a comentario **criado pelo proprietario** em uma PR aberta e interna, com formato exato `AUREN_TESTE_V1 pytest <sha40>`.
- O assistente pode comentar em PR pelo conector GitHub sem exigir formulario do usuario: prova de autoria em PR #108, comentario #6100770444 (apenas sonda, sem teste).
- Validacao roda em runner hospedado: confere evento, privacidade, proprietario, PR nao-draft, base main, repositorio sem fork e SHA exato do HEAD.
- Job Windows baixa controlador do commit imutavel `448a1f87a672278471d1d8dcc08a2a621e10b77c`, baixa PR em pasta separada e roda apenas `pytest` pelo watchdog limitado, sem OPENAI_API_KEY.
- Logs e JUnit sao artefatos do GitHub e o assistente pode buscar os resultados pelo conector.
- **BLOQUEIO DE ATIVACAO:** `before-job.ps1` e configurado exclusivamente no Windows e ainda nao foi atualizado para permitir o novo workflow/evento. Nao considerar pronto ate verificar e aprovar localmente a politica, sem diminuir os bloqueios existentes, e realizar teste final real com PR inofensiva.
- O teste de PR nao altera a instalacao principal do Auren. Atualizacao da main principal e um fluxo separado, para nao substituir o Auren em uso por codigo nao aprovado.

### Organizacao da raiz (2026-10-10)

- 11 arquivos `.bat` realocados para `scripts/iniciar`, `scripts/instalar`, `scripts/testar`, `scripts/diagnosticos` e `scripts/experimentos`.
- Todos os atalhos agora fixam cwd na raiz via `%~dp0..\\..` para preservar paths de `.venv`, `requirements*.txt`, `tests/` e `voice/`.
- Tres scripts Python auxiliares independentes de diagnostico movidos para `scripts/diagnosticos`, com bootstrap corrigido.
- `testes_auren.py`, `testes_auren_live.py`, `medir_metricas_router.py` e `medir_router_baseline.py` permanecem como entradas Python legadas utilizadas por outros modulos/testes, para nao quebrar integracoes; `README.md` aponta para os novos atalhos.
- Nenhuma mudanca no Harness, Dispatcher, Router ou voz. PR #110 incorporada; CI Linux/Windows passou, mas os atalhos ainda precisam ser abertos manualmente no Windows para validar a experiencia real.

### Interface desktop — primeira entrega visivel (2026-10-10)

- Nova entrada opcional `scripts/iniciar/ABRIR_AUREN_GUI.bat` -> `interface_auren.py`, com Tkinter da biblioteca padrao, escuro, chat por texto, estado inicial Desligado e botoes Ativo/Standby/Desligado.
- `ui/backend.py` serializa comandos em uma thread e usa apenas `auren.criar_harness(confirmation_channel=...)` e `harness.processar_mensagem`, preservando Router/Dispatcher/PermissionManager e memoria/sessao existentes.
- Confirmacoes sensiveis aparecem em janela autorizar/negar, com timeout que **nega**; fechar a UI pede cancelamento cooperativo, rejeita confirmacoes pendentes e encerra sessao ao concluir.
- Voz/PTT permanece em `scripts/iniciar/AUREN_VOZ.bat`; interface MVP e **texto somente**. Nao foi feito um redesenho do pipeline de voz.
- PR #109 integrada na main; CI: suite completa Linux **503 passed/15 skipped**, testes focados Linux **135 passed/6 skipped** e Windows **141 passed**. Interface Tk completa exige teste visual em Windows real antes de declarar experiencia operacional validada.
- Esta tarefa substitui temporariamente refinamentos de navegador e correcoes de runner como foco unico. **Nao** reabrir todas as PRs antigas nem expandir a UI antes da primeira validacao.

### Primeira correcao da bateria Windows real — clipboard

- Relatorio real da bateria ALL: [execucao #37886243164](https://github.com/Yamatosemj/aurenOFC/actions/runs/37886243164), commit `394a8cd8`. O watchdog terminou sem travar (`completed`), mas a suite terminou com exit code 1; houve PASS em varias operacoes Windows e FAIL em clipboard, interacoes integradas e outras expectativas.
- Falha reproduzivel de clipboard: leitura retornou `name '_user32' is not defined`. Causa: `tools/windows_clipboard.py` referenciava helper ausente; implementacao revisada usa `ctypes.windll.user32` diretamente na inicializacao da API, com assinaturas Win64 preservadas.
- Regressao em `tests/test_windows_clipboard.py` simula as DLLs sem tocar a area de transferencia real e roda no CI focado Linux/Windows.
- A PR #107 foi incorporada na main e passou nos testes citados; esta etapa trata somente a inicializacao da API do clipboard. Ainda nao ha repeticao comprovada de leitura/escrita em Windows real no novo SHA. As demais falhas da bateria ficam para tarefas isoladas posteriores.

### Seguranca A01 — incorporada na main (PR #99)

- A falha anterior fazia leituras externas ja marcadas como nao confiaveis deixarem de ativar a guarda de confirmacao. Corrigida na main pelo merge da PR #99.
- `tools/dispatcher.py` registra a fonte em toda leitura bem-sucedida de `ler_arquivo`, `ler_pagina` e `obter_contexto_navegador`, mesmo com a flag previamente ativa.
- Regressoes: tres casos reproduziram falha antes da correcao; depois, suite completa do CI Linux retornou 445 passed e 6 skipped.
- Esta correcao nao implementa A02/A03. O A04 tambem foi incorporado na main pela PR #104.

### Seguranca A04 — bloqueio absoluto integrado na main (PR #104)

- `core/permission_manager.py` tinha precedencia incorreta: apos conteudo externo, uma capacidade `BLOCKED` contada podia virar `CONFIRM`.
- `PermissionManager` agora aplica `BLOCKED` antes da guarda de origem externa; AUTO ainda sobe para CONFIRM apos leitura nao confiavel.
- Testes para ambos os cenarios passaram na PR #104, assim como o teste A01 ajustado sem contornar a protecao de AppData no Windows.
- A02 foi corrigido na branch da PR #81 por merge da PR #100 (`12b72d1`), com aprovacao obrigatoria antes do import. As PRs #81/#84 ainda nao foram incorporadas a `main` e seguem exigindo revisao de conflitos e integracao. A03 (pesquisa web) tambem permanece fora da `main`.

### Confirmacao por voz — PR #105 incorporada na main

- Em V47, a confirmacao podia consumir audio antigo da fila e nao verificava estritamente o envelope de `CapturedAudio`.
- Agora descarta a fila antes do prompt, aceita somente um envelope `("audio", CapturedAudio)` novo e exige afirmacao explicita. Negacao e resposta ambigua nao autorizam.
- Comandos de saida textuais/falados aceitam pontuacao mantendo correspondencia exata.
- CI da PR #105: suite completa Linux 494 passed/15 skipped, focused Linux 119 passed/6 skipped e focused Windows 125 passed.
- O codigo especifico desta correcao foi portado da PR #92 para a V47. Ao integrar a cadeia V48 (#85, #90, #92, #95), reconciliar as alteracoes duplicadas; nao executar merge cego nem tratar como validacao fisica de microfone.

### Preservacao de origem visual — PR #106 incorporada na main

- O Dispatcher reconstruia `ToolResult` ao anexar `vision_coordinate_transform`, mas perdia `conteudo_nao_confiavel`; a reconstrucao agora preserva a marca de proveniencia.
- Regressao testada para sucesso e falha, incluindo `for_model()`, `as_dict()`, `error_code` e metadados de geometria.
- CI da PR #106: suite completa Linux 496 passed/15 skipped, focused Linux 128 passed/6 skipped e focused Windows 134 passed.
- Nao substitui exercicios reais de visao+acao+verificacao no Windows.

### CI de revisao de PRs (PR #104)

- Workflows de pytest completo e testes focados agora usam `pull_request` para a `main` em runners hospedados do GitHub, alem do push normal.
- Regressao de prompt injection incluida na bateria focada Linux/Windows.
- Na PR #104, o workflow completo Linux e os dois jobs focados Linux/Windows concluiram com sucesso.
- Ainda falta validar a bateria funcional live de Auren+modelo+navegador no PC, independente da suite pytest.

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

## Automação remota de testes — 2026-10-09

- Workflow manual pytest nos runners do GitHub disponível, com logs e JUnit.
- Repositório confirmado privado nesta inspeção.
- Workflow manual de conexão Windows preparado, sem checkout/imports do Auren.
- Runner Windows local foi registrado e conexao validada na execucao #37884137457; atualizacao remota da main validada na #37890091132.
- Workflow live foi habilitado com supervisao e limites; tentativas iniciais de ALL revelaram erros de descoberta/aliases posteriormente corrigidos. Nao ha evidencia aqui de validacao funcional ALL completa.
- Estado e próximos passos: [Testes pelo GitHub](docs/TESTES_GITHUB.md).
