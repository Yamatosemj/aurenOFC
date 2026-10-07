# Auren — Estado oficial do projeto

> Fonte de verdade operacional do Auren.
> Antes de iniciar uma nova tarefa, compare este arquivo com a branch/PR, o head da main e o CI do GitHub.
> Historico, memorias da conversa e documentos arquivados nao substituem este estado.

Atualizado em: 2026-10-07

## Estado atual

- Versao estavel: V47
- Modelo padrao: gpt-5.6-luna
- Branch/PR ativa: fix/browser-click-new-tab-page / PR #77
- Head da main: 0a8304e1b097d458511f017ca1f0d9da19d86726
- Head da branch ativa: 07b565e1f49a1cb3162f55799bbaecaa58683f9a
- Ultimo head funcional validado: b72e43f3c04f6866f90340d1df2d3ec6782ab7b5
- Baseline de pytest em 2026-10-07: 576 passed, 5 warnings
- Tarefa atual: Tarefa 2 — memoria recuperavel sob demanda
- Proxima tarefa apos o portao: Tarefa 3 — undo reversivel
- Fase do projeto: Browser Intelligence

## Roadmap Mark

O Mark-LV e referencia de ideia, problema e casos-limite. Nao e fonte de codigo para copia. Cada implementacao do Auren deve ser escrita de forma independente, usando sua arquitetura, nomes em portugues e ToolResult.

| Ordem | Tarefa | Origem no Mark-LV | Alvo principal no Auren | Estado |
|---|---|---|---|---|
| 0 | Kit de continuidade | padrao de continuidade do projeto | docs/PROMPT_BASE.md, docs/NOTAS_DE_PASSAGEM.md, docs/REFERENCIA_MARK.md, AUREN_STATE.md | CONCLUIDA |
| 1 | Timeout, retry, escada de modelos e cooldown | core/gemini.py | providers/model_ladder.py, provider/config/usage/testes | CONCLUIDA |
| 2 | Memoria recuperavel sob demanda | main.py, memory/memory_manager.py | memory/store.py, tools/memory.py | ATUAL |
| 3 | Undo reversivel | core/undo.py | core/ + ferramentas reversiveis | BACKLOG |
| 4 | Confirmacao humana nao-forjavel | core/confirm.py, ui.py | core/permission_manager.py, voice/confirmation.py | BACKLOG / PARCIAL |
| 5 | Selecao de dispositivos de audio | core/audio_devices.py | voice/input.py, voice/tts.py | BACKLOG |
| 6 | Continuidade de sessao | main.py | provider + Harness + memoria | BACKLOG |
| 7 | Wake word + PTT/ack | core/wake_word.py, core/hotkey.py | camada de voz | BACKLOG / PARCIAL |
| 8 | Avatar + visemes/lip-sync | core/avatar.py, core/viseme.py, ui.py | nova camada visual | BACKLOG |
| 9 | Video/HUD/theming | ui.py | nova camada visual/configuracao | BACKLOG |
| 10 | Historico/uso remoto/extensoes | roadmap LVI+ em readme.md | novo transporte/modulos remotos + Harness | BACKLOG |

## Decisao de continuidade entre modelos

A documentacao oficial atual da OpenAI descreve previous_response_id como mecanismo de continuidade multi-turno e permite informar um model por resposta, mas nao afirma que um previous_response_id seja portavel quando a solicitacao muda de modelo. Por isso o Auren adota uma politica conservadora:

- a primeira tentativa usa previous_response_id somente no primeiro degrau
- ao trocar de modelo, o provider remove previous_response_id e envia historico_completo
- sem historico_completo, a troca falha com o erro estruturado model_ladder_history_required, em vez de perder contexto silenciosamente
- o fluxo atual do Harness nao usa response_id entre rodadas

Fontes consultadas em 2026-10-07:
- https://developers.openai.com/api/reference/python/resources/responses/methods/create
- https://developers.openai.com/api/docs/guides/migrate-to-responses
- https://github.com/openai/openai-python

## Decisoes da Tarefa 1

- Timeout padrao: 30 s, configuravel por AUREN_REQUEST_TIMEOUT_S. O SDK documenta 600 s como default atual.
- max_retries: 0. O Auren controla fallback por degrau; o SDK nao repete automaticamente antes do cooldown.
- Cooldowns: 300 s para 429, 1800 s para 503/504 e timeout, 21600 s para 404.
- 400/401 nao trocam de modelo.
- AUREN_MODEL continua sempre como primeiro degrau; AUREN_MODEL_LADDER apenas adiciona degraus posteriores e remove duplicatas.
- Sem AUREN_MODEL_LADDER, o degrau selecionado continua sendo somente AUREN_MODEL.
- Nenhuma dependencia nova foi adicionada.

## Backlog

- Tarefa 2 — memoria recuperavel sob demanda
- Tarefa 3 — undo reversivel
- Tarefa 4 — confirmacao humana nao-forjavel
- Tarefa 5 — selecao de dispositivos de audio
- Tarefa 6 — continuidade de sessao
- Tarefa 7 — wake word + PTT/ack
- Tarefa 8 — avatar + visemes/lip-sync
- Tarefa 9 — video/HUD/theming
- Tarefa 10 — historico/uso remoto/extensoes

## Registro final da Tarefa 1

- Tarefa 1 concluida e validada no CI.
- Full pytest Linux: 589 passed, 6 skipped, 5 warnings.
- Full pytest Windows: 595 passed, 5 warnings.
- Static checks: verdes.
- Nao houve alteracao de Browser/Windows; portanto o runner live manual nao e requisito desta tarefa.
- O runtime permanece em V47; a proxima frente e a Tarefa 2.
