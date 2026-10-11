# Auren — Estado oficial do projeto

> Fonte de verdade operacional do Auren.
> Antes de iniciar uma nova tarefa, compare este arquivo com a branch/PR, o head da main e o CI do GitHub.
> Histórico, memórias da conversa e documentos arquivados não substituem este estado.

Atualizado em: 2026-10-10

## Estado atual

### Etapa 9 — Testes, CI e controle remoto (2026-10-10)

- **Auditoria documental submetida na [PR #129](https://github.com/Yamatosemj/aurenOFC/pull/129):** branch `docs/etapa-9-testes-ci-controle-remoto` sobre a `main` `1bb85bc04efe850cd0705652c54e5cddcee9a8bd`; novo `docs/architecture/09-testes-ci-controle-remoto.md`, manutenção dos guias `docs/TESTES_GITHUB.md` e `docs/CONTROLE_REMOTO_GITHUB.md`, referências em README/AGENTS/inventário. **Somente Markdown**; sem alteração de workflow, runner, código, política, segredos ou permissões.
- **Código confrontado:** sete workflows `.github/workflows/`, `pytest.ini`, `remote_tests/chat_request.py`, `pr_job.py`, `windows_watchdog.py`, política complementar de chat, tester manual `testes_auren_live.py`, scripts de autorização e testes de contratos, segurança, PowerShell, CI e descoberta Live. Commits fixados de validador/controlador confrontados por blob com a `main`.
- **Descoberta confirmada:** pytest por comentário **já funcionou de ponta a ponta** para a PR #119, SHA `9fa20a4cb92dfead9a77fa9356d8677bcf559be8`, no [run #38085000162](https://github.com/Yamatosemj/aurenOFC/actions/runs/38085000162): jobs `validar` e `executar` success, log `PR test: completed; exit=0`, artifact publicado. Antigos avisos de que nunca funcionou foram corrigidos. **Não comprova disponibilidade atual do runner nem autorização contínua.**
- **Separação operacional:** CI de PR roda em Linux/Windows hospedados; testes por comentário fazem apenas pytest sem API no self-hosted Windows após autenticação e política local; despacho manual pode testar PR ou atualizar main; workflow Live exige aprovações específicas, SHA revisado e é capaz de executar efeitos/API. `testes_auren_live.py` fica fora da coleta pytest e L3 permanece reservada.
- **Segurança/limites:** `before-job.ps1` e arquivos de aprovação estão no PC e não foram inspecionados; runner self-hosted não é sandbox; watchdog tem limites de 20 min, 120 s sem saída, 16 MiB log, Job Object e STOP-LIVE, mas não reverte efeitos externos. Testes hospedados e histórico não provam Live/hardware atual.
- **Evidência documental:** 72 links relativos nos sete Markdown conferidos (0 quebrados). GitHub Actions do primeiro HEAD da [PR #129](https://github.com/Yamatosemj/aurenOFC/pull/129) `c384889b6a3a1efaf7e0df415950362adf073e5b`: [Linux completo](https://github.com/Yamatosemj/aurenOFC/actions/runs/38098663088) **556 passed/24 skipped**; [focados Linux/Windows](https://github.com/Yamatosemj/aurenOFC/actions/runs/38098662980) Linux **166 passed/15 skipped**, Windows hospedado **181 passed** e modo seguro **110 passed** por sistema. Revalidar no último HEAD após este registro; não foi enviado comentário de teste, acionada Action manual, executado Windows pessoal, Live nem API nesta auditoria.
- **Próxima área após revisão/merge:** Etapa 10 — entradas, configuração e distribuição, PR separada.


### Etapa 8 — Skills, capacidades e experimentos (2026-10-10)

- **Etapa 8 integrada na [PR #128](https://github.com/Yamatosemj/aurenOFC/pull/128), merge `1bb85bc04efe850cd0705652c54e5cddcee9a8bd`:** branch `docs/etapa-8-skills-capacidades-experimentos` sobre a `main` `186b783965229a2578191a7337d4ed82228e0923`. Novo `docs/architecture/08-skills-capacidades-extensibilidade.md` e referências em README, AGENTS e inventário. **Apenas Markdown**, sem instalar skills, ativar experimentos, alterar runtime, workflow, testes ou permissões.
- **Código confrontado:** `skills/loader.py`, `core/session.py`, `auren.py`, Harness, Router, `core/capabilities.py`, `core/capability_resolver.py`, `core/intent_resolver.py`, TaskSpec, `core/local_decision.py`, fast paths, `core/capability_audio_runtime.py`, experimento/matriz, scripts da flag e `experimental/wake_word.py`; testes de catálogo, áudio, TaskSpec, roteamento e prompt injection.
- **Estado real:** carregador de `SKILL.md` integrado ao contexto, mas nenhum `SKILL.md` versionado em `skills/` na `main`; 14 capacidades declaratórias não são as 49 ferramentas executáveis; resolver de TaskSpec é separado do roteamento normal; flag `AUREN_EXPERIMENT_CAPABILITY_AUDIO` fica desligada por padrão e, quando ativada, só tenta volume/mudo/mídia pelo Dispatcher; wake word permanece fora do runtime PTT.
- **Limites para investigação posterior:** `install()` não valida explicitamente diretório/`..`/symlinks ao aceitar nomes de skills; texto de skills não é fronteira forte de confiança; padrão lexical não garante relevância; fallback do experimento pode retornar ao fluxo normal após falha de execução; ausência de testes dedicados de skills e ausência de validação de wake word real. Registrar hipóteses, não corrigir nesta PR.
- **Evidência de validação:** 88 links relativos conferidos sem erros. GitHub Actions do primeiro HEAD revisado `d56255cdd28d0517b2027ca898180f5a9a04a645`: [Linux completo](https://github.com/Yamatosemj/aurenOFC/actions/runs/38097910114) **556 passed/24 skipped**; [focados Linux/Windows](https://github.com/Yamatosemj/aurenOFC/actions/runs/38097910125) Linux **166 passed/15 skipped**, Windows **181 passed** e modo seguro **110 passed em cada sistema**. Conferir CI novamente no último HEAD após registrar esta evidência. Sem skills de terceiros, Windows Live, API, wake word físico nem experimento de áudio acionado nesta etapa documental.
- **Próxima etapa iniciada em branch separada:** 9 — testes, CI e controle remoto.


### Etapa 7 — Interface desktop e GUI (2026-10-10)

- **Etapa 7 integrada na [PR #127](https://github.com/Yamatosemj/aurenOFC/pull/127), merge `186b783965229a2578191a7337d4ed82228e0923`:** branch `docs/etapa-7-interface-desktop-gui` sobre a `main` `89755a2705b08b241e9f5e019b62f41ccda3d30d`. Novo documento `docs/architecture/07-interface-desktop-gui.md` e referências em README, AGENTS e inventário. **Apenas Markdown**, sem alterar runtime, dependências, testes, runner nem políticas.
- **Código confrontado:** `interface_auren.py`, `ui/backend.py`, `core/confirmation.py`, `auren.py`, `core/harness.py`, `core/task_manager.py`, `core/session.py`, launcher da GUI; testes `tests/test_desktop_ui_backend.py`, `tests/test_confirmation.py`, `tests/test_cancellation_harness.py`, `tests/test_scripts_layout.py` e regressões de Router.
- **Limites anotados:** GUI Tkinter é texto e canal do mesmo Harness; worker serializado por filas e geração de sessão; Ativo habilita envio, Standby bloqueia só UI (não cancela atividade nem desabilita worker), Desligado solicita cancelamento cooperativo e descarte enfileirado; confirmação modal expira em 45 s e nega por padrão; resposta de tarefa em andamento pode chegar após Desligado, pois não é filtrada por geração depois da execução; conversa visível não é apagada ao desligar.
- **Validação documental:** 65 links relativos conferidos sem caminhos quebrados. GitHub Actions do primeiro HEAD revisado `0a3f24fa884e2531ba38544852ad4cf385d4e48e`: [Linux completo](https://github.com/Yamatosemj/aurenOFC/actions/runs/38097470177) **556 passed/24 skipped**; [focados Linux/Windows](https://github.com/Yamatosemj/aurenOFC/actions/runs/38097470147) Linux **166 passed/15 skipped**, modo seguro Linux **110 passed**, Windows **181 passed** e modo seguro Windows **110 passed**. **Conferir novamente o HEAD final após atualizar estes documentos.** Não foi executada janela Tk real, teste físico Windows, API, Live ou notebook pessoal. Não interpretar pytest de backend como prova do layout/fechamento físico.
- **Próxima área já iniciada em branch separada:** Etapa 8 — skills, recursos experimentais e extensibilidade.


### Etapa 6 — Voz, STT e TTS (2026-10-10)

- **Etapa 6 integrada na [PR #126](https://github.com/Yamatosemj/aurenOFC/pull/126), merge `89755a2705b08b241e9f5e019b62f41ccda3d30d`:** branch `docs/etapa-6-voz-stt-tts` criada sobre a `main` `7a13c412463ad55ef7fe5562ad2e757feb2cebde`. Novo documento `docs/architecture/06-voz-stt-tts.md` e links de manutenção em README, AGENTS e inventário. **Somente Markdown**, nenhum runtime, workflow, dependência, política ou runner alterado.
- **Código confrontado:** entrada `voice/main.py`, captura `input.py`, segmento `segmentation.py`, ASR `stt.py`, TTS `tts.py`, formatação e confirmação falada; locks de áudio, script de inicialização/instalação/diagnóstico, factory do Harness, testes `test_voice.py`, `test_voice_v3.py`, `test_confirmation.py` e scripts.
- **Estado real:** Voice Engine interno V4 com evolução candidata V48 integrada via PR #119; versão técnica global continua V47. Hotkey ativa Ctrl direito + Shift direito; PTT, pré/pós-roll, VAD WebRTC/fallback energia, Parakeet INT8 e Kokoro ONNX locais. O Harness usa o mesmo Router/Dispatcher e canal de autorização por voz.
- **Limites notáveis para tarefas futuras:** stream do microfone aberto antes da hotkey; primeiras cargas podem baixar modelos; VAD/STT/TTS não avaliados fisicamente; métricas de latência são parciais; scripts exibem V3 enquanto engine se intitula V4; docstring de interrupção ainda cita F8, mas modo ativo usa Ctrl direito + Shift direito; instalador apaga diretório ASR completo se existente apesar de texto sobre cache incompleto. Registrar como diferenças/hipóteses, não corrigir nesta PR.
- **Evidência de validação:** 72 links relativos conferidos sem erros. No primeiro HEAD revisado `371418434518a050c822e7edf3c473c53dd152dc`, [Linux completo](https://github.com/Yamatosemj/aurenOFC/actions/runs/38096946269) aprovou **556 passed/24 skipped**; [Linux/Windows focados](https://github.com/Yamatosemj/aurenOFC/actions/runs/38096946329) aprovaram Linux **166 passed/15 skipped**, Windows **181 passed** e modo seguro **110 passed** em cada sistema. Revalidar os checks no SHA final após registrar esta evidência. **Nenhum teste físico de microfone, áudio, PTT, tempo real, API ou Live realizado**. Não elevar V48 a validada.
- **Próximo subsistema já iniciado separadamente:** Etapa 7 — interface desktop/GUI.


### Etapa 5 — Navegador e Browser Intelligence (2026-10-10)

- **Etapa 5 integrada na [PR #125](https://github.com/Yamatosemj/aurenOFC/pull/125), merge `7a13c412463ad55ef7fe5562ad2e757feb2cebde`**, branch `docs/etapa-5-navegador-browser-intelligence` sobre a `main` `946f21e2b3d629ce4e8e157ded5dc97c4d1e65d4`. Novo `docs/architecture/05-navegador-browser-intelligence.md` e referências em README/AGENTS/INVENTARIO. Apenas Markdown; não alterar runtime, workflows, testes, políticas ou runner.
- **Lido e confrontado:** `tools/browser.py`, `tools/browser_context.py`, `tools/browser_reading.py`, `tools/browser_elements.py`, `tools/browser_navigation.py`, `core/browser_verification.py`, `core/harness_heuristics.py`, `core/harness_multitab.py`, `core/harness_tools.py`, `core/harness_cycle.py`, `core/harness_guards.py`, Router/Dispatcher, contratos, PermissionManager e testes browser/Harness/segurança relevantes.
- **Comportamentos e limites documentados:** Chromium Playwright em perfil persistente/global ao processo, 14 tools browser; leitura do DOM resumida/truncada e às vezes com rolagem; contexto unificado marcado não confiável; seleção heurística de elementos; verificação extra somente em objetivos compostos detectados e somente para algumas ações; uma mutação posterior substitui estado anterior; conteúdo do site nunca autoriza ação por si só.
- **Pontos a investigar em tarefas específicas:** `ler_pagina` pode rolar mesmo como leitura; `obter_contexto_navegador` retorna `ok=True` quando `ler_pagina` devolve texto de erro; cliques/teclas/fechamento e outras ações não possuem comparador determinístico e podem esgotar guard em tarefas compostas; perfil não é isolado por chat. Não declarar vulnerabilidade comprovada sem reprodução.
- **Validação documental:** 76 links relativos entre cinco Markdown conferidos na árvore (0 quebrados). Checks hospedados do primeiro HEAD revisado `e3ac3a9e2640309a90e2f7f4473d2236fe2b29ae` aprovados: [Linux completo](https://github.com/Yamatosemj/aurenOFC/actions/runs/38096229205) **556 passed/24 skipped**, [focados Linux/Windows](https://github.com/Yamatosemj/aurenOFC/actions/runs/38096229199) Linux **166 passed/15 skipped**, Windows **181 passed**, modo seguro **110 passed** em cada sistema. Verificar CI novamente no HEAD efetivo antes do merge; sem Playwright Live, site externo, API, login ou teste no notebook pessoal.
- **Próximo subsistema já iniciado em branch separada:** Etapa 6 — voz, STT e TTS.


### Etapa 4 — Windows, arquivos e visao (2026-10-10)

- **Etapa 4 integrada na [PR #124](https://github.com/Yamatosemj/aurenOFC/pull/124), merge `946f21e2b3d629ce4e8e157ded5dc97c4d1e65d4`:** branch `docs/etapa-4-windows-arquivos-visao` a partir da `main` `d0c9c991a3311127f59368d123020b2c065f1e1f`. Novo `docs/architecture/04-windows-arquivos-visao.md` e referencias em README, AGENTS e inventario. **Apenas Markdown**; nenhum runtime, workflow, politica ou runner alterado.
- **Fontes lidas:** fachadas e modulos Windows de janelas, UIA, input/DPI, screenshot, processos, audio, clipboard e status; applications, files, file_intelligence, Dispatcher, PermissionManager, core/vision e guards do Harness. Contratos confrontados com o registry de 49 tools e testes existentes.
- **Limites:** buscar/inspecionar/ler arquivo nao implementam move/rename/undo; arquivo fora da allowlist pede confirmacao, caminho sensivel bloqueia; UIA e alvos de janelas dependem do provedor/interface real; imagem exige snapshot consistente e DPI validado para conversao segura; clique/arraste requerem politica e posterior verificacao quando aplicavel.
- **Evidencia de validacao:** 76 links relativos conferidos sem caminhos ausentes. GitHub Actions do commit documental `c80aaadefb49a3455dd1294fb914e78c59561bf2`: [Linux completo](https://github.com/Yamatosemj/aurenOFC/actions/runs/38095610847) **556 passed/24 skipped**; [focados Linux/Windows](https://github.com/Yamatosemj/aurenOFC/actions/runs/38095610844) Linux **166 passed/15 skipped**, modo seguro Linux **110 passed**, Windows **181 passed** e modo seguro Windows **110 passed**. Checks devem ser conferidos novamente no HEAD efetivo antes de mesclar. Sem Live ou notebook pessoal. Nenhum teste Live, API, mouse, screenshot, UIA ou Windows pessoal executado nesta etapa documental.
- **Proxima área já iniciada separadamente:** Etapa 5 — navegador e Browser Intelligence.


### Etapa 3 — modelo, sessao/contexto e memoria (2026-10-10)

- **Etapa 3 integrada na [PR #123](https://github.com/Yamatosemj/aurenOFC/pull/123), merge `d0c9c991a3311127f59368d123020b2c065f1e1f`:** `docs/architecture/03-modelo-sessao-memoria.md`, com referencias em AGENTS/README/INVENTARIO. Base auditada `a4ddb8a9f01b0cefa0d7233ac8714d4539a8502b`; apenas Markdown, sem alterar runtime, testes, workflows ou permissoes.
- **Escopo concluido da leitura:** provider/Responses, config/fachada/prompt, contexto e continuacao das rodadas, SQLite e migracao, fatos globais versus chats, escrita automatica, esquecimento, cache e metricas.
- **Validacao local:** 66 testes focados aprovados no Linux do ambiente de trabalho (Python 3.12, pytest 8.3.5, jsonschema 4.26.0). Reproducoes adicionais com banco temporario e provider/cliente falsos. Resultados do CI hospedado estao nos checks e na descricao da PR #123, associados ao SHA efetivo. Nao e teste no notebook pessoal; sem Live/API/microfone.
- **Pendencias reproduzidas, nao corrigidas:** (1) AUREN_MODEL diferente do padrao aborta import auren; README agora explica a limitacao, (2) context.build sem chat_id recupera conversas/estrategias globais embora turnos seja vazio; Harness normal fornece ID, (3) cache de chamadas diretas nao diferencia response_id; estado normal do Harness e inelegivel ao cache.
- **Limites documentados:** esquecer remove apenas fato pela chave; filtro de credenciais e lexical; proveniencia de conteudo externo nao e preservada estruturalmente na memoria; recusas ok=False do store podem nao gerar diagnostico; custo usa coeficientes fixos, nao cotacao.
- **Proximo passo historico cumprido:** PR #123 passou CI e foi integrada; Etapa 4 iniciada separadamente. Correcoes de runtime exigem tarefas proprias.

### Etapa 2 — auditoria estatica do caminho de ferramentas e permissoes (2026-10-10)

- **Escopo auditado:** documentacao de `core/router.py`, `core/local_decision.py`, `core/tools_registry.py`, `core/tool_contracts.py`, `tools/dispatcher.py`, `core/permission_manager.py`, `core/confirmation.py`, `core/tool_result.py`, atalhos e entrada experimental de audio.
- **Etapa 2 integrada:** [PR #122](https://github.com/Yamatosemj/aurenOFC/pull/122), merge `01899563695e552a16f79852a21296b441575129`. Entrega: `docs/architecture/02-roteamento-seguranca.md`, mais referencias em `AGENTS.md`, `README.md` e `docs/INVENTARIO.md`. Exclusivamente Markdown, nenhum runtime/politica alterados.
- **Responsabilidades confirmadas estaticamente:** Router escolhe caminhos/tools, nao autoriza; fast path e chamadas do modelo convergem no Dispatcher; schema/contrato antes de autorizar; PermissionManager combina capacidade, argumentos e estado da tarefa; ToolResult fornece sucesso estruturado ao ciclo.
- **Politica real:** AUTO/CONFIRM/BLOCKED; limite padrao de 10 tentativas contaveis, guard de falhas repetidas e protecao contra conteudo externo nao confiavel para proximas acoes contaveis. TextConfirmationChannel nega interacao no AUREN_TEST_MODE; nao assumir mesmo comportamento para todo canal injetado.
- **Pontos para teste/decisao futuros, sem runtime alterado:** validador local implementa subconjunto de JSON Schema; marca de fonte nao confiavel permanece ate reiniciar tarefa (nao so ate primeira aprovacao); fast path ainda adapta retorno textual; heuristicas de alvo nao garantem semantica real da interface. Nao declarar vulnerabilidade exploravel sem reproduzir.
- **Validação concluída:** 70 links internos verificados sem caminhos quebrados. CI da PR #122 no SHA `a45d173fa99cd66ce6764a657838947a14389dfc`: Linux **556 passed, 24 skipped**, Windows hospedado focado **181 passed**, modo seguro Windows **110 passed**; Linux focado **166 passed, 15 skipped** e modo seguro **110 passed**. **Nao houve testes Live/API ou pytest no notebook pessoal**, pois esta PR so altera Markdown. **Proxima area:** Etapa 3 — provider/modelo, sessao/contexto e memoria.


### Etapa 1 - auditoria estatica do nucleo (2026-10-10)

- **Etapa 1 concluida:** [PR #121](https://github.com/Yamatosemj/aurenOFC/pull/121) integrada a `main` (merge `c6fdfa60e34dea6b72abaffc79844877d9061f11`), auditoria estatica do nucleo/Harness, dos dois Orchestrators, TaskManager, sessao/contexto, trace e fila de estrategia. Etapa 2 posteriormente concluida na PR #122; proxima etapa 3.
- **Entrega:** `docs/architecture/01-nucleo.md`, com fluxo rastreado no codigo real, mapa de responsabilidades, estados/transicoes, fast path, guards de visao/browser, limites, mecanismos de contexto/persistencia, matriz de testes e orientacoes de manutencao. `docs/INVENTARIO.md`, `README.md` e `AGENTS.md` atualizados.
- **Escopo estrito:** apenas Markdown, **sem alterar runtime, segurança, politicas do Windows, workflow ou API**.
- **Evidencia de auditoria e CI confirmada:** leitura dos arquivos do ciclo e testes de ownership, ferramenta, guard, estados, session, trace, cancelamento, execucao unica e roteamento. PR #121 HEAD `9edb1ae7101fa9a3f1b6483a484ee3d4883a5014`, GitHub Actions completo Linux **556 passed / 24 skipped**, testes focados Windows hospedado **181 passed**, seguro Windows **110 passed**; testes Linux focados **166 passed / 15 skipped** e seguro **110 passed**. **Sem pytest no notebook pessoal e sem testes Live nesta PR**, pois somente Markdown foi alterado.
- **Observacoes nao reproduzidas:** (1) docstring de input da rodada cita reasoning, mas construcao examinada anexa function_call + outputs, (2) sinalizador de falha nao recuperada e atualizado por chamada e pode perder falha anterior da mesma rodada, (3) retries internos nao devem ser confundidos com limite absoluto de chamadas ao provider, (4) fase do AgentOrchestrator nao e estado terminal operacional. Registrar como hipoteses para testes focados futuros, nao como bugs confirmados.
- **Validacao adiada:** teste Live, modelo real, interface/desktop, voz, API, interrompimento de operacoes externas e rollback. **Proxima etapa:** documentacao do caminho de ferramentas e seguranca (Router, Dispatcher, contratos e permissoes), sem nova funcionalidade fora do escopo.


### Documentacao e continuidade — etapa 0 (2026-10-10)

- **Prioridade decidida pelo proprietario:** documentar o Auren **subsistema por subsistema**, antes de abrir novas implementacoes; cada area deve ser mapeada, auditada no codigo, confrontada com seus testes e documentada em PR focalizada.
- **Etapa 0 documentada e integrada:** [PR #120](https://github.com/Yamatosemj/aurenOFC/pull/120) adicionou `AGENTS.md`, `docs/INVENTARIO.md`, links no `README.md` e este marco do estado. CI Linux e Windows hospedado aprovados. **Nao alterou runtime, workflows nem politicas do runner.**
- **Inventario inicial confirmado:** 220 arquivos versionados, 22 diretorios e 49 entradas de ferramenta em `core/tools_registry.py` na revisao da main de 2026-10-10. Dez areas foram **mapeadas, nao auditadas integralmente**.
- **Proxima tarefa apos a etapa 0:** auditar com profundidade o nucleo de execucao (`core/harness.py`, `core/harness_*.py`, `agent/orchestrator.py`, gerenciamento de tarefas); documentar arquitetura real, limites e testes. Uma PR separada.
- **Divida documental conhecida:** `AUREN_STATE.md` longo, com historico misturado; `docs/CONTROLE_REMOTO_GITHUB.md` e `docs/TESTES_GITHUB.md` contêm orientacoes e marcos antigos de testes que precisam ser reconciliados com a operacao comprovada do pytest remoto. Corrigir em PRs proprias sem enfraquecer seguranca.
- **Importante:** a V48 de voz segue sem validacao fisica; este trabalho documental nao altera sua prontidao. **Proxima etapa: auditoria do nucleo de execucao**, em PR separada.


### Integracao V48 voz/STT - candidata (2026-10-10)

- Prioridade ativa: reconciliar PRs encadeadas **#85, #90, #92, #95** sobre a `main` atual, **sem** merge cego das branches antigas e sem reverter as correcoes de seguranca e UI posteriores.
- Nova branch `integrate/v48-voice-stt-ptt`: transplante de `voice/input.py`, `voice/segmentation.py`, `voice/stt.py`, `voice/main.py`, `voice/list_devices.py`, `voice/__init__.py`, `tests/test_voice.py` e `requirements-voice.txt` da ponta da cadeia #95. `voice/confirmation.py` e TTS foram comparados e ja coincidem com a `main`; `config.py`, `auren.py`, Dispatcher, permissoes, CI de autorizacao e interface permanecem como estao na `main`.
- Escopo: PTT Ctrl direito + Shift direito, pre/post-roll, VAD WebRTC + fallback de energia, nao enviar silencio ao ASR, fallback seguro de taxa nativa do microfone, ASR 16 kHz, aquecimento e recuperacao de falha de captura.
- `webrtcvad-wheels==2.0.14.post1` permanece dependencia opcional do modo voz no requirements-voice separado e pinado.
- **Somente pytest** hoje: executar CI Linux e Windows hospedado e testes unitarios de voz/microfone/VAD simulados, depois pytest remoto em PR via ChatGPT. Nao executar `testes_auren_live.py`, nao iniciar microfone, nao consumir API e nao alegar validação fisica de latencia/STT. V47 permanece versao estavel ate testar com hardware.
- **CI e resultado remoto confirmados:** PR #119 integrada apos suite completa Linux **556 passed / 24 skipped**, Windows hospedado focado **181 passed**, modo seguro Windows **110 passed**, Linux focado **166 passed / 15 skipped**. No Windows pessoal, [run #38085000162](https://github.com/Yamatosemj/aurenOFC/actions/runs/38085000162), PR #119 commit `9fa20a4cb92dfead9a77fa9356d8677bcf559be8`: **579 passed, 1 skipped, 1 warning, zero falhas**, pytest 26.83 s, exit code 0; relatórios PR e XML entregues ao chat.
- **Ainda nao validado:** latencia real, PTT Ctrl direito + Shift direito em hardware, captura de microfone fisico, qualidade STT e VAD com ambiente real; tambem testes Live/API. Nenhum foi executado nesta rodada.
- **Proxima tarefa sugerida:** quando o proprietario tiver acesso ao PC, fazer teste pequeno de voz/PTT, sem expandir escopo; antes disso, no maximo auditoria pontual de static/pytest. Nao mesclar branches antigas em cascata.


### Revisao das 11 falhas da PR-sonda (2026-10-10)

- Escopo exclusivo da rodada: corrigir testes deterministas para rodarem no Windows real com `AUREN_TEST_MODE=1`; **sem mexer nas implementacoes de producao, nas protecoes do runner nem nas camadas Live**.
- Testes de confirmacao interativa: `tests/test_confirmation.py` simula entrada apenas com `monkeypatch.delenv` dentro do proprio teste e acrescenta verificacao especifica de bloqueio no modo seguro; `tests/test_execution_single_path.py` e `tests/test_visual_coordinate_dispatcher_integration.py` recebem canais de confirmacao falsos injetados em `PermissionManager`, com handlers ja simulados.
- Teste de arquivos `tests/test_file_intelligence.py` grava bytes UTF-8 exatos para impedir que `Path.write_text` converta LF em CRLF no Windows antes da leitura; implementacao de `read_file` permanece preservando bytes/quebras originais.
- CI hospedado Linux e Windows agora executa as quatro familias focalizadas com `AUREN_TEST_MODE=1` em passo adicional e isolado. A suite normal continua sendo executada.
- **Pendencias menores:** um teste de symlink ignorado por falta de privilegio de criacao de link simbolico no runner Limited; um warning `PytestUnhandledThreadExceptionWarning` por decodificacao UTF-8 do subprocesso PowerShell em `tests/test_chat_policy_setup.py`. Sem justificativa para ampliar permissoes do runner; registrar para ajuste futuro.
- **Resultado:** GitHub Actions [run #38082122839](https://github.com/Yamatosemj/aurenOFC/actions/runs/38082122839) realizou pytest no notebook do proprietario para PR #118 (commit `b3950b628818ed64381c1d64dff750bf2cbda9a8`): 557 aprovados, 0 falhas, 1 ignorado, 1 aviso, exit_code 0. Artefatos `pr-result.json`, `pr-test.log`, `pytest.xml` publicados e analisados diretamente pelo chat. PR #118 integrada na main.

### Marco: primeira execucao completa do pytest no notebook (2026-10-10)

- O proprietario confirmou aplicacao local de `scripts/instalar/ATUALIZAR_WORKFLOW_CHAT_ASCII.ps1`. ChatGPT publicou na PR #108 comentario #6101499200 com SHA `03ee21db3c4fecd0cab8385af4a72e7f74b935e9`.
- [GitHub Actions run #38081143327](https://github.com/Yamatosemj/aurenOFC/actions/runs/38081143327): `validar=success`; o job `executar` rodou no notebook, hook local autorizou, checkouts controlador/PR foram feitos e `pytest` **executou de verdade** por 25,25 s. Publicados como artifact os arquivos `pr-result.json`, `pr-test.log`, `pytest.xml`.
- Resultado remoto da PR-sonda **naquele commit**: **500 passed, 11 failed, 1 skipped** (512 coletados), exit code 1. `pr-result.json` registra `reason=completed`, `duration_seconds=26.74`. O workflow foi marcado failure porque a suite da PR falhou; **isso nao e falha de disparo/runner**.
- Das 11 falhas, 9 sao testes que esperam confirmacao interativa aprovada, mas a politica segura do runner executa `AUREN_TEST_MODE=1` e nega a acao; 2 sao diferencas de quebras de linha `\\n` versus `\\r\\n` em testes de leitura de MD/CSV no Windows. Um teste de symlink foi pulado por ausencia de privilegio de criar symlink; manter usuario com `RunLevel=Limited`.
- Esta PR-sonda e antiga, de alteracao documental; nao concluir a partir dela que o `main` atual tem exatamente 11 falhas. Ajustar os testes/harness sem afrouxar politica de autorizacao antes de considerar o pytest **verde** no notebook.
- **Marco atingido:** objetivo de disparar teste pelo chat e receber resultado real automaticamente no Windows esta operacional para pytest de PR aberta. **Nao equivale a suite 100% verde nem valida ferramentas live/API.**



- **Versão estável:** V47
- **Modelo padrão:** `gpt-5.6-luna`
- **Ultima PR documental integrada:** #122 (Router, Dispatcher, contratos e permissoes), apos #121 (nucleo/Harness) e #120 (inventario/AGENTS.md). PR #119 consolidou voz candidata V48. Consultar GitHub para PRs abertas; branches antigas de voz nao devem ser mescladas cegamente.
- **Head da main:** consultar GitHub antes de cada tarefa; ultimo merge de codigo confirmado: PR #119 (`e9712ef5257b971c3aefc6ed1e6911ad4ae5b8d9`)
- **CI:** PR #119 Linux completo 556 passed/24 skipped; Windows hospedado focado 181 passed, modo seguro Windows 110 passed. **Notebook pessoal PR #119: 579 passed, zero falhas, 1 skipped, 1 warning, run #38085000162.**
- **Fase atual:** Etapas documentais **0, 1 e 2 integradas**. Etapa 3 documentada em PR propria, com testes locais focados; conferir bloco mais recente acima para CI e integracao. **Proxima area documental: 4 (Windows, arquivos e visao)**. Voz V48 ainda sem validacao fisica; testes Live adiados.

### Primeiro teste desbloqueado no Windows, falha de parser ASCII (2026-10-10)

- O proprietario informou a instalacao do fluxo sem GCM. ChatGPT comentou na PR #108 e disparou [run #38080418175](https://github.com/Yamatosemj/aurenOFC/actions/runs/38080418175). O job hospedado `validar` passou, o runner pessoal autorizou o job local e clonou controlador fixado e SHA da PR.
- O pytest **nao foi iniciado**: Windows PowerShell 5.1 nao analisou a linha do workflow `"### Auren no Windows — PR #$env:PR_NUMBER"`, que apareceu como `â€”` e levantou `UnexpectedToken` antes da execucao do watchdog.
- Alteracao pontual: trocar travessao Unicode por hifen ASCII na linha de resumo; workflow muda de blob SHA `90e3e3070f8b977bc328dc6ad72b112407ffeb3d` para `52abfd109c06cdc458727337579984d91da879bc`. Preservar estrutura de jobs, autorizacao e controller fixado.
- `scripts/instalar/ATUALIZAR_WORKFLOW_CHAT_ASCII.ps1`: migrar **uma vez por aprovacao local** politica offline e `chat-control-approval.json` para novo blob, criar backups e preservar hook principal, controle manual e STOP-LIVE.
- Testes no Windows hospedado aprovaram a migracao (180 testes focados), PR #117 integrada. Proximo passo: usuario roda um unico `git pull` + `scripts/instalar/ATUALIZAR_WORKFLOW_CHAT_ASCII.ps1`, e ChatGPT repete sonda PR #108.
- A falha original de GCM foi superada; ainda falta validacao real do pytest no notebook.

### Decisao de risco explicita: autorizacao local offline (2026-10-10)

- O proprietario deixou claro que prefere **reduzir atrito** e aceita um risco delimitado para concluir a automacao agora; nao quer mais ciclos de diagnosticos de GCM no Windows.
- Antes desta tarefa, [run #38079480204](https://github.com/Yamatosemj/aurenOFC/actions/runs/38079480204) mostrou GCM falhando mesmo apos ajuste de cwd; nunca houve execucao de pytest no notebook.
- Novo `remote_tests/chat-control-functions.ps1`: nao consulta Git/GCM/API. Validacao online de PR aberta interna, proprietario e SHA exato continua no job `validar` hospedado do workflow existente, com controlador Python de SHA fixo; o hook local confirma evento, origem privada, ator proprietario, workflow esperado, job `executar`, formato de comando, SHA de 40 caracteres, primeira tentativa, nao-admin e STOP-LIVE.
- `scripts/instalar/AUTORIZAR_TESTES_CHAT_SEM_GCM.ps1` exige **execucao expressa no PC**: backup de `chat-control-functions.ps1` e `chat-control-approval.json`, copia apenas politica complementar e inclui `offline_hosted_validation=true` nessa aprovacao especifica. Preserva controle legado e `before-job.ps1`. Instalador nao altera o workflow.
- **Risco assumido:** sem consulta remota a partir do Windows, uma alteracao maliciosa/comprometimento do workflow em `main` pode ficar fora do alcance da verificacao local. A checagem `workflow_blob` e a aprovacao local continuam como metadados, mas deixam de constituir atestacao remota do blob ativo; confiamos no GitHub e na conta do proprietario. Nao prometer isolamento perfeito do pytest: o codigo da PR roda como usuario runner, sem privilégios elevados.
- CI Linux e Windows hospedado aprovado; PR #116 integrada. Proximo passo: usuario executa uma unica vez `git pull --ff-only` + `scripts/instalar/AUTORIZAR_TESTES_CHAT_SEM_GCM.ps1` e responde com saida, entao ChatGPT dispara PR #108 e le resultados. **Sistema ainda nao comprovado no notebook.**

### Bloqueio confirmado apos aplicar #115 (2026-10-10)

- O proprietario aplicou com sucesso `CORRIGIR_CREDENCIAL_CHAT.ps1`, com backup e verificacoes preservados, apos `git pull --ff-only` da main.
- Sonda disparada pelo ChatGPT na PR #108 (comentario #6101265370), [run #38079480204](https://github.com/Yamatosemj/aurenOFC/actions/runs/38079480204): `validar=success`, GitHub encaminhou ao runner `auren-windows-authorized`, hook local recusou `executar` no `Set up runner`: **`Credencial Git/GCM do runner: processo terminou com erro.`** Nenhum pytest executou no PC.
- Portanto, **ajuste de cwd e instalador nao resolveram**. Nao repetir `git pull`/instalador ou prometer automacao pronta sem rever a estrategia de credenciais.
- Caminho tecnico a avaliar: mover toda verificacao online de comentario, PR, SHA e workflow para um controlador confiavel e fixado do GitHub Actions, mantendo no Windows uma politica local *offline* restrita a workflow/commit fixos. Assim o hook nao precisa recuperar credenciais Git no inicio de cada job. Precisa validar cuidadosamente eventos, autorizacao e integridade antes de alterar o hook.
- A configuracao atual permanece com bloqueio fail-closed. Nenhuma nova permissao foi liberada.

### Bloqueio do instalador de credenciais (2026-10-10)

- O proprietario fez `git pull` para a PR #114 integrada e executou `CORRIGIR_CREDENCIAL_CHAT.ps1`. O instalador abortou na verificacao de fonte anterior, com `Politica instalada nao corresponde a versao esperada; parada segura.`
- Erro confirmado no instalador: marcador foi escrito `credencial.interactive=never credential fill`, mas Git usa `credential.interactive=never credential fill`. A rejeicao aconteceu antes de copiar backup/modificar arquivo; nenhuma correcao GCM foi instalada por essa tentativa.
- Corrigido o marcador na PR #115 e testado no Windows hospedado executando o instalador real contra politica temporaria, incluindo sucesso/idempotencia/rejeicao sem mutacao. Instalacao no PC do proprietario e execucao remota real ainda pendentes.
- **Nao alegar que o runner remoto esta pronto**: apos CI e aplicacao local pontual, repetir PR-sonda. `AUREN_STATE.md` registra esse bloqueio e a solucao.

### Ajuste de credenciais do runner (em validacao, 2026-10-10)

- `AurenAuthorizedRunner` executa com usuario `victo`, `LogonType=Interactive` e `RunLevel=Limited`; nao alterar para admin ou para outro tipo de logon para contornar a falha.
- Hipotese tecnica: o pre-job herda cwd/configuracao Git diferente da sessao PowerShell, possivelmente um checkout anterior. Em `chat-control-functions.ps1`, a consulta nao-interativa de credencial passa a usar `git -C <USERPROFILE> ... credential fill`, fora do checkout do runner; nao adiciona credenciais nem altera validacoes.
- Se GCM ainda falhar, erro seguro discrimina processo encerrado com falha de timeout (sem imprimir tokens ou mensagens sensiveis).
- `scripts/instalar/CORRIGIR_CREDENCIAL_CHAT.ps1`: copia so a politica complementar, cria backup e valida autorizacao existente; requer execucao unica autorizada pelo proprietario.
- **Nao declarar corrigido ate teste de ponta a ponta no notebook.** GitHub-hosted Windows/CI nao equivale ao runner real.

### Diagnostico de autenticacao do runner real (2026-10-10)

- O proprietario instalou com sucesso a politica de testes por chat e ativou log do motivo do bloqueio no hook `before-job.ps1`.
- A partir do chat, comentario na PR #108 iniciou [workflow #38077526737](https://github.com/Yamatosemj/aurenOFC/actions/runs/38077526737): `validar` passou, runner `auren-windows-authorized` recebeu o job, mas a verificacao local retornou `Verificacao remota indisponivel; job bloqueado` antes de executar pytest.
- O proprietario executou verificacoes na sessao interativa do PowerShell: credencial Git e APIs `repo`, `PR` e `jobs` todas passaram; nao comprova que esses recursos funcionam com identidade/ambiente do processo do runner e nao cobriu a chamada `contents/.github/workflows/auren-chat-tests.yml?ref=<sha>`.
- Diagnostico adicional instalado pelo proprietario: [run #38078450858](https://github.com/Yamatosemj/aurenOFC/actions/runs/38078450858), job `validar=success`, `executar` bloqueado com motivo **`Etapa credencial Git/GCM indisponivel no contexto do runner`**. O runner consegue iniciar, mas `git credential fill` em modo nao interativo falha no contexto do job; as quatro verificacoes anteriores passaram no PowerShell interativo. **Nao esta resolvido.** Proxima triagem: consultar tipo de logon e conta da tarefa agendada `AurenAuthorizedRunner` sem expor credenciais; nao afrouxar politica nem afirmar sucesso do pytest.
- Proxima correcao: acrescentar mensagens **apenas com a etapa** da falha nas 4 chamadas ao helper da politica (GCM, conteudo de workflow, PR, validacao hospedada), sem registrar token nem liberar operacoes. `scripts/instalar/DIAGNOSTICAR_TESTES_CHAT.ps1` faz backup e substitui somente a funcao complementar do chat. `before-job.ps1`, approval original e workflow imutavel continuam intocados.
- PR #113 integrada apos CI verde; apos `git pull` e execucao local expressa de `scripts/instalar/DIAGNOSTICAR_TESTES_CHAT.ps1`, repetir PR #108 pelo comentario. **Ainda nao considerar testes reais operacionais.**

### Configuracao pontual da politica Windows (2026-10-10)

- `remote_tests/chat-control-functions.ps1`: controle complementar exclusivo de `issue_comment`, negacao por padrao, runner nao-administrador, proprietario, projeto privado, comentario exato, PR aberta no mesmo repositorio com SHA imutavel e job hospedado `validar` bem-sucedido.
- Workflow `auren-chat-tests.yml`: validador agora fixo no commit imutavel `b695fad7cc668d9a47e4dfc72f11a74b152d9cac`. Conteudo do workflow no Git tem blob SHA aprovado `90e3e3070f8b977bc328dc6ad72b112407ffeb3d`; a politica local verifica esse SHA para evitar aprovar automaticamente alteracoes futuras da main.
- Instalador `scripts/instalar/AUTORIZAR_TESTES_CHAT.ps1` modifica apenas `before-job.ps1` no Windows apos criar backup, copia as regras extras e gravacao de aprovacao separada; preserva a funcao de controle manual antiga. Exige uma execucao explicita pelo usuario no PC.
- Testes em `tests/test_chat_policy_setup.py` verificam conteudo imutavel e, em hosted Windows, sintaxe/comportamento com caminho temporario. Nao modifica a politica pessoal durante testes.
- PR #112 incorporada na main e passou em CI hospedado; **ainda nao operacional no notebook** ate o proprietario executar a instalacao unica e fazermos uma PR-sonda real pelo chat.
- Testar PR no Windows pessoal nao e sandbox. Rodar somente PR propria revisada, sem reintroduzir acesso a chaves API e sem rodar em administrador.

### Testes Windows solicitados diretamente pelo chat (em preparacao, 2026-10-10)

- Nova workflow `.github/workflows/auren-chat-tests.yml` responde somente a comentario **criado pelo proprietario** em uma PR aberta e interna, com formato exato `AUREN_TESTE_V1 pytest <sha40>`.
- O assistente pode comentar em PR pelo conector GitHub sem exigir formulario do usuario: prova de autoria em PR #108, comentario #6100770444 (apenas sonda, sem teste).
- Validacao roda em runner hospedado: confere evento, privacidade, proprietario, PR nao-draft, base main, repositorio sem fork e SHA exato do HEAD.
- Job Windows baixa controlador do commit imutavel `448a1f87a672278471d1d8dcc08a2a621e10b77c`, baixa PR em pasta separada e roda apenas `pytest` pelo watchdog limitado, sem OPENAI_API_KEY.
- Logs e JUnit sao artefatos do GitHub e o assistente pode buscar os resultados pelo conector.
- **BLOQUEIO DE ATIVACAO CONFIRMADO:** `before-job.ps1` e configurado exclusivamente no Windows e ainda nao foi atualizado para permitir o novo workflow/evento. Nao considerar pronto ate verificar e aprovar localmente a politica, sem diminuir os bloqueios existentes, e realizar teste final real com PR inofensiva.
- **Execucao de verificacao:** [run #38076073679](https://github.com/Yamatosemj/aurenOFC/actions/runs/38076073679) — comentario pelo ChatGPT na PR #108 (#6100813538), `validar=success`, runner `auren-windows-authorized` iniciou o job, mas `before-job.ps1` bloqueou a execucao antes dos passos. A politica local ainda precisa ser inspecionada/atualizada pelo proprietario.
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

**Prioridade atual:** consolidar as PRs encadeadas da V48 de voz/STT por testes deterministas e integrar sem regressões em segurança.

**Fica pendente:** execução de testes Live com microfone, PTT, latência, navegador/modelo e L4/L5 quando o proprietário estiver disponível. Não confundir pytest com validação física.

**Browser Intelligence:** refinamentos por tipo de ação permanecem no backlog da tarefa anterior; não abrir uma segunda frente simultaneamente.

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
