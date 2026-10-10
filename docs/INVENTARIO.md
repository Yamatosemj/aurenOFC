# Inventario tecnico e plano de documentacao do Auren

> **Inventario das etapas 0 a 6.** Este documento e um mapa para orientar auditorias **uma por vez**; a presenca de um arquivo no repositorio nao comprova que a funcionalidade opera de ponta a ponta. Areas marcadas como **mapeadas** ainda nao foram auditadas em detalhe. As Etapas 1 a 6 documentam nucleo, caminho de ferramentas, modelo, memoria, Windows, visao, navegador e voz por leitura de codigo e testes; **isso nao comprova comportamento Live**.

## Escopo conferido

- Fonte: arvore recursiva da `main` do GitHub, consultada em **2026-10-10**; **220 arquivos versionados e 22 diretorios**. O numero e um retrato dessa revisao, nao uma contagem que deve ser mantida manualmente.
- O codigo de `core/tools_registry.py` continha **49** entradas de ferramenta (`type: function`) nesse levantamento; confirme novamente se o registry mudar.
- Versao configurada em `config.py`: **V47**. A candidata a voz **V48 foi integrada a `main`** pela PR #119, mas continua sem prova de funcionamento fisico do PTT/microfone/latencia. Alteracao de codigo integrada nao significa recurso validado em ambiente real.
- `pytest` da PR #119 foi aprovado no notebook Windows do proprietario: **579 passed, 1 skipped, 1 warning** ([execucao](https://github.com/Yamatosemj/aurenOFC/actions/runs/38085000162)). Isso nao representa teste Live de API, microfone ou automacao.
- `AUREN_STATE.md` possui historico acumulado e anotacoes antigas; sua reorganizacao em estado conciso e historico selecionado e uma tarefa documental **pendente**.

## Mapa dos subsistemas

| Ordem sugerida | Subsistema | Fontes principais no repositorio | Situacao documental |
| --- | --- | --- | --- |
| 1 | **Nucleo e execucao de tarefas** | `core/harness.py`, `core/harness_*.py`, `agent/orchestrator.py`, `core/orchestrator.py`, `core/task_manager.py`, `core/task_trace.py` | **Auditado estaticamente** em [architecture/01-nucleo.md](architecture/01-nucleo.md); testes pytest/CI e limites descritos; **Live nao validado** |
| 2 | **Roteamento, ferramentas e seguranca** | `core/router.py`, `core/local_decision.py`, `core/tools_registry.py`, `core/tool_contracts.py`, `core/permission_manager.py`, `tools/dispatcher.py`, `core/tool_result.py` | **Auditado estaticamente** em [architecture/02-roteamento-seguranca.md](architecture/02-roteamento-seguranca.md); testes/limites explicados; **Live não validado** |
| 3 | **Modelo, sessoes e memoria** | `providers/openai_provider.py`, `core/response.py`, `core/session.py`, `core/memory_context.py`, `memory/store.py`, `tools/memory.py` | **Auditado estaticamente** em [architecture/03-modelo-sessao-memoria.md](architecture/03-modelo-sessao-memoria.md); reproducoes locais e pytest focado; **API/Live nao validados** |
| 4 | **Windows, arquivos e visao** | `tools/windows.py`, `tools/windows_*.py`, `tools/applications.py`, `tools/files.py`, `tools/file_intelligence.py`, `core/vision.py` | **Auditado estaticamente** em [architecture/04-windows-arquivos-visao.md](architecture/04-windows-arquivos-visao.md); limites de UIA, caminhos, DPI e testes simulados; **Live nao validado** |
| 5 | **Navegador** | `tools/browser.py`, `tools/browser_*.py`, `core/browser_verification.py`, `core/harness_*.py` | **Auditado estaticamente** em [architecture/05-navegador-browser-intelligence.md](architecture/05-navegador-browser-intelligence.md); Playwright, DOM, abas, política e verificação parcial; **Live não validado** |
| 6 | **Voz, STT e TTS** | `voice/*.py`, `requirements-voice.txt`, `scripts/iniciar/AUREN_VOZ.bat`, `agent/ari_native/audio_manager.py` | **Auditado estaticamente** em [architecture/06-voz-stt-tts.md](architecture/06-voz-stt-tts.md): PTT, captura, VAD, ASR, TTS, confirmações e limites; **teste físico pendente** |
| 7 | **Interface desktop** | `interface_auren.py`, `ui/backend.py`, `scripts/iniciar/ABRIR_AUREN_GUI.bat` | Mapeado; **auditoria detalhada pendente** |
| 8 | **Skills, recursos experimentais e extensibilidade** | `skills/loader.py`, `core/capabilities.py`, `core/capability_audio_*.py`, `experimental/` | Mapeado; **nao presumir recursos habilitados** |
| 9 | **Testes, CI e controle remoto** | `tests/`, `pytest.ini`, `testes_auren_live.py`, `remote_tests/`, `.github/workflows/` | Mapeado; **documentacao operacional desatualizada em partes** |
| 10 | **Entradas, configuracao e distribuicao** | `main.py`, `auren.py`, `config.py`, `scripts/`, `requirements*.txt`, `README.md` | Mapeado; **auditoria detalhada pendente** |

**Mapeado** significa apenas que confirmamos a presenca dos caminhos e identificamos seu papel geral nos arquivos consultados. **Auditado** exigira examinar implementacao, consumidores, limites, testes, dependencias e efeito real. Nenhuma area recebe o rótulo de auditada apenas por ter passado no pytest.

### Entradas e componentes de referencia

- `main.py` / `auren.py`: entrada e fachada de inicializacao do Auren; `auren.py` oferece `criar_harness()`.
- `core/harness.py`: ciclo de tarefas; outros arquivos `core/harness_*.py` agrupam etapas e protecoes.
- `core/router.py`: dono da selecao local e da lista de ferramentas por contexto; `tools/dispatcher.py` faz a ponte com handlers e devolve `ToolResult`.
- `core/permission_manager.py`: confirmacao, bloqueios e limites de acoes. **As politicas e testes reais prevalecem sobre qualquer resumo.**
- `tools/windows.py` e `tools/browser.py`: fachadas de submodulos respectivos; nao copiar suas responsabilidades para novas fachadas sem avaliar limites.
- `memory/store.py`: persistencia SQLite; nao confundir com propostas de memoria avancada em PRs ainda abertas.
- `voice/main.py`: orquestracao de entrada de voz, STT e TTS; a interface Tkinter continua sendo entrada **textual** independente.
- `remote_tests/` e `.github/workflows/`: testes e controle remoto com politicas sensiveis. Codigo do repo **nao reflete sozinho** autorizacoes locais no Windows.

## Documentos preexistentes que exigem revisao

| Documento | Situacao identificada | Acao futura |
| --- | --- | --- |
| `README.md` | Traz instalacao, arquitetura e status do GUI/voz | Manter introdutorio; mover explicacoes extensas apenas quando auditorias estiverem completas |
| `AUREN_STATE.md` | Mistura estado recente, marcos e resultados historicos, com aproximadamente 31 mil caracteres | Reorganizar **sem perder evidencias** e sem tratar texto antigo como status atual |
| `docs/CONTROLE_REMOTO_GITHUB.md` | Contem avisos antigos de que o teste por comentario/runner ainda nao estava operacional | Reconciliar com os runs atuais, preservando limites e procedimentos de seguranca |
| `docs/TESTES_GITHUB.md` | Registra passos historicos de configuracao e operacao do runner | Diferenciar instalacao, autorizacao, teste remoto pytest e teste Live; verificar contra workflows e runs |
| `scripts/README.md` | Indice dos atalhos existentes | Manter como referencia operacional local |

**Nao apagar ou simplificar procedimentos de autorizacao, rollback ou recuperacao sem conferir os scripts reais e as condicoes do runner pessoal.**

## Como vamos auditar cada area

1. Conferir arquivos, imports, chamadas, registro de capacidades e dependencia entre componentes.
2. Identificar **implementado**, **testado com mocks/CI**, **validado fisicamente** e **experimental ou pendente**, sempre separadamente.
3. Conferir testes relevantes e caminhos de falha/seguranca; nao atribuir garantia que o teste nao fornece.
4. Produzir ou atualizar **um documento tecnico por necessidade concreta**, com links para o codigo (nao colar implementacoes).
5. Abrir uma PR documental focalizada, rodar verificacoes e registrar lacunas. Ao final da auditoria, marcar a area como auditada neste inventario.

## Ordem de trabalho

**Etapa 0 (concluida na [PR #120](https://github.com/Yamatosemj/aurenOFC/pull/120)):** mapeamento do repositorio, criacao de `AGENTS.md` e indice de manutencao. Nenhuma mudanca de runtime.

**Etapa 1 (concluida na [PR #121](https://github.com/Yamatosemj/aurenOFC/pull/121)):** auditoria estatica de **nucleo de execucao** (Harness, **dois** Orchestrators com funcoes distintas, TaskManager, contexto, trace, fila pos-tarefa) em [architecture/01-nucleo.md](architecture/01-nucleo.md), confrontando codigo e contratos com testes. Registrar observacoes como hipoteses sem alterar runtime. Validacao fisica/Live continua pendente.

**Etapa 2 (concluida na [PR #122](https://github.com/Yamatosemj/aurenOFC/pull/122)):** Router, selecao/atalhos, registry, ToolContract, Dispatcher, PermissionManager, confirmacoes, ToolResult e protecao de origem nao confiavel, documentados em [architecture/02-roteamento-seguranca.md](architecture/02-roteamento-seguranca.md). Auditoria estatica e testes hospedados; **nao** inclui runtime, notebook pessoal ou hardware real.

**Evidencia de CI da Etapa 2:** PR #122 aprovada nos GitHub Actions no SHA `a45d173fa99cd66ce6764a657838947a14389dfc`: Linux 556 passed /24 skipped; testes focados Windows hospedado 181 passed e modo seguro Windows 110 passed. Foram conferidos 70 links relativos sem erros. Nenhum teste Live ou no notebook pessoal foi solicitado.

**Etapa 3 (integrada na [PR #123](https://github.com/Yamatosemj/aurenOFC/pull/123)):** modelo/provider, sessao/contexto, memoria SQLite, cache e uso em [architecture/03-modelo-sessao-memoria.md](architecture/03-modelo-sessao-memoria.md). 66 testes locais focados aprovados; reproducoes sinteticas confirmaram override bloqueado na fachada, busca global sem chat_id e identidade incompleta no cache de chamadas diretas. CI da PR deve ser conferido no SHA efetivo; nenhuma alteracao de runtime.

**Etapa 4 (integrada na [PR #124](https://github.com/Yamatosemj/aurenOFC/pull/124), merge `946f21e2b3d629ce4e8e157ded5dc97c4d1e65d4`):** Windows, arquivos, UI Automation, screenshot, conversao de coordenadas e limites de permissao em [architecture/04-windows-arquivos-visao.md](architecture/04-windows-arquivos-visao.md). Somente Markdown; 76 links relativos conferidos sem erros. O CI hospedado do HEAD final `2fd5a0e651bcaabdb44d1b901dd98353acac6b77` passou: Linux completo 556 passed/24 skipped; Linux focado 166 passed/15 skipped, Windows focado 181 passed, modo seguro 110 passed por sistema. **Nao foi executada validacao fisica/Live.**

**Etapa 5 (integrada na [PR #125](https://github.com/Yamatosemj/aurenOFC/pull/125), merge `7a13c412463ad55ef7fe5562ad2e757feb2cebde`):** navegador Playwright/Chromium, perfil persistente, leitura DOM, abas, Router/Dispatcher, proteção de origem, Browser Intelligence e guards em [architecture/05-navegador-browser-intelligence.md](architecture/05-navegador-browser-intelligence.md). Auditoria estática; 76 links relativos conferidos (0 quebrados). Checks do primeiro HEAD revisado `e3ac3a9e2640309a90e2f7f4473d2236fe2b29ae` aprovados: Linux completo 556 passed/24 skipped, Linux focado 166 passed/15 skipped, Windows 181 passed, modo seguro 110 passed por sistema. Verificar novamente HEAD final; sem Live.

**Etapa 6 (em auditoria documental nesta branch):** pipeline PTT, VAD, Parakeet local, Kokoro, canal de confirmação, modelos, scripts de instalação e limites dos testes em [architecture/06-voz-stt-tts.md](architecture/06-voz-stt-tts.md). Somente Markdown. CI, links e revisão da PR própria pendentes; sem teste físico.

**Proxima area documental:** Etapa 7 — interface desktop e GUI.

**Evidencia de CI da Etapa 1:** PR #121 aprovada no GitHub Actions, SHA de codigo documental antes do merge `9edb1ae7101fa9a3f1b6483a484ee3d4883a5014`: Linux 556 passed/24 skipped, Windows hospedado focado 181 passed e modo seguro 110 passed. **Sem execucao Live, microfone ou testes no notebook pessoal nessa PR documental.**

**Etapas posteriores:** seguir a ordem da tabela, ajustando prioridades com o proprietario quando necessario. A reorganizacao de `AUREN_STATE.md` e a correcao da documentacao de testes remotos devem receber PRs proprias, separadas de mudancas no runtime.

Quando surgir contradicao entre texto e codigo, registre-a como pendencia, identifique a origem e verifique o GitHub antes de declarar uma versao como atual.
