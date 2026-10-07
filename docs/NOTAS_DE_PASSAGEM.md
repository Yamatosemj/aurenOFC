# Notas de passagem

## Modelo

> Tarefa concluida: (numero e nome)
> Arquivos criados/alterados:
> Decisoes tomadas (e por que):
> Testes: (comando, numero de testes antes e depois, resultado)
> Ficou pendente / virou backlog:
> Proxima tarefa: (numero)

---

## 2026-10-07 — Tarefa 1 — Timeout, retry e escada de modelos com cooldown

Tarefa concluida: 1 — Timeout, retry e escada de modelos com cooldown

Arquivos criados/alterados:
- providers/model_ladder.py
- providers/openai_provider.py
- config.py
- core/usage.py
- tests/test_model_ladder.py
- tests/test_model_config.py
- AUREN_STATE.md
- docs/NOTAS_DE_PASSAGEM.md

Decisoes tomadas (e por que):
- O SDK recebe timeout explicito e max_retries=0; o fallback fica sob controle unico do Auren.
- AUREN_MODEL permanece o primeiro degrau. AUREN_MODEL_LADDER apenas adiciona degraus posteriores.
- 429 -> 5 min; 503/504 e timeout -> 30 min; 404 -> 6 h. 400/401 nao trocam.
- Ao trocar de modelo durante uma conversa com previous_response_id, o provider exige historico_completo e envia esse historico sem o ID.
- Nenhuma dependencia nova foi adicionada.

Testes:
- Baseline antes: 576 passed, 5 warnings
- Comando: py -m pytest -q
- CI pos-commit: aguardando.

Ficou pendente / virou backlog:
- A execução live `python testes_auren_live.py --rapido` não se aplica: esta tarefa não mexe em Browser/Windows.
- Tarefa 2 — memória recuperável sob demanda — passa a ser a próxima tarefa.


Proxima tarefa: 2
