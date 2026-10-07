# Notas de passagem

## Modelo

> Tarefa concluída: (número e nome)
> Arquivos criados/alterados:
> Decisões tomadas (e por quê):
> Testes: (comando, nº de testes antes e depois, resultado)
> Ficou pendente / virou backlog:
> Próxima tarefa: (número)

---

## 2026-10-07 — Tarefa 0 — Kit de continuidade

**Tarefa concluída:** 0 — Kit de continuidade

**Arquivos criados/alterados:**
- `docs/PROMPT_BASE.md`
- `docs/NOTAS_DE_PASSAGEM.md`
- `docs/REFERENCIA_MARK.md`
- `AUREN_STATE.md`

**Decisões tomadas (e por quê):**
- Mantida a versão técnica **V47**: a tarefa é exclusivamente documental e não altera runtime.
- Registrado o PR **#77**, branch `fix/browser-click-new-tab-page`, HEAD final `8ed44a5b562bb33835d1771e4a05f38b15bb1914`.
- O baseline de hoje foi fixado em **576 testes aprovados**.
- A documentação separa o que já existe no Auren do que é somente referência de ideia do Mark-LV; tarefas 2–10 não são tratadas como especificações de implementação.
- A licença **CC BY-NC 4.0** do Mark-LV é respeitada: esta documentação referencia arquivos e ideias, não código ou comentários para cópia.

**Testes:**
- Comando de referência: `py -m pytest -q`
- Antes: **576 passed**
- Depois: **576 passed** como baseline de runtime, pois a mudança é exclusivamente documental.
- Resultado verificado no CI do PR #77 antes deste commit documental, no merge ref `4139b0696fe1e378d80fccb8541e6232b91d01b5`: **576 passed, 5 warnings, 57.44s**.
- O novo commit não altera runtime; o workflow visual disparado para ele está aguardando execução. Não há um resultado pós-commit do pytest disponível neste momento, então ele não é apresentado como uma execução nova.

**Ficou pendente / virou backlog:**
- Tarefa 1 — Timeout, retry e escada de modelos com cooldown — é a próxima tarefa técnica.
- Tarefas 2–10 permanecem backlog/documentação de planejamento.
- A execução manual L4/L5 do runner live continua sendo obrigação da fase Browser Intelligence; esta tarefa não mexeu no Browser.

**Próxima tarefa:** 1
