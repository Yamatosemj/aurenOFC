# Inventario tecnico e plano de documentacao do Auren

> **Etapa 0 — levantamento inicial.** Este documento e um mapa para orientar auditorias **uma por vez**; a presenca de um arquivo no repositorio nao comprova que a funcionalidade opera de ponta a ponta. Areas marcadas como **mapeadas** ainda nao foram auditadas em detalhe. A Etapa 1 documenta o nucleo por leitura de codigo e analise de testes; **isso nao comprova comportamento Live**.

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
| 2 | **Roteamento, ferramentas e seguranca** | `core/router.py`, `core/local_decision.py`, `core/tools_registry.py`, `core/tool_contracts.py`, `core/permission_manager.py`, `tools/dispatcher.py`, `core/tool_result.py` | Mapeado; **auditoria detalhada pendente** |
| 3 | **Modelo, sessoes e memoria** | `providers/openai_provider.py`, `core/response.py`, `core/session.py`, `core/memory_context.py`, `memory/store.py`, `tools/memory.py` | Mapeado; **auditoria detalhada pendente** |
| 4 | **Windows, arquivos e visao** | `tools/windows.py`, `tools/windows_*.py`, `tools/applications.py`, `tools/files.py`, `tools/file_intelligence.py`, `core/vision.py` | Mapeado; **auditoria detalhada pendente** |
| 5 | **Navegador** | `tools/browser.py`, `tools/browser_*.py`, `core/browser_verification.py` | Mapeado; **auditoria detalhada pendente** |
| 6 | **Voz, STT e TTS** | `voice/*.py`, `requirements-voice.txt`, `scripts/iniciar/AUREN_VOZ.bat` | Mapeado; **teste fisico pendente** |
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

**Etapa 0 (esta PR):** mapear o repositorio, criar `AGENTS.md` e centralizar o indice de manutencao. Nenhuma mudanca de runtime.

**Etapa 1 (esta PR):** auditar estaticamente **nucleo de execucao** (Harness, **dois** Orchestrators com funcoes distintas, TaskManager, contexto, trace, fila pos-tarefa) em [architecture/01-nucleo.md](architecture/01-nucleo.md), confrontando codigo e contratos com testes. Registrar observacoes como hipoteses sem alterar runtime. Validacao fisica/Live continua pendente.

**Etapa 2 (proxima area sugerida):** Router, ferramentas, Dispatcher, contratos e permissoes; documentar a fronteira de seguranca e executar testes automatizados, em PR independente.

**Etapas posteriores:** seguir a ordem da tabela, ajustando prioridades com o proprietario quando necessario. A reorganizacao de `AUREN_STATE.md` e a correcao da documentacao de testes remotos devem receber PRs proprias, separadas de mudancas no runtime.

Quando surgir contradicao entre texto e codigo, registre-a como pendencia, identifique a origem e verifique o GitHub antes de declarar uma versao como atual.
