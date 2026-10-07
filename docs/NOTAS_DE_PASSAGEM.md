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
- Registrado o PR **#77**, branch `fix/browser-click-new-tab-page`, HEAD `627b305dd433ebb7603f40507847f707533bf794`.
- O baseline de hoje foi fixado em **576 testes aprovados**.
- A documentação separa o que já existe no Auren do que é somente referência de ideia do Mark-LV; tarefas 2–10 não são tratadas como especificações de implementação.
- A licença **CC BY-NC 4.0** do Mark-LV é respeitada: esta documentação referencia arquivos e ideias, não código ou comentários para cópia.

**Testes:**
- Comando de referência: `py -m pytest -q`
- Antes: **576 passed**
- Depois: **576 passed**
- Resultado verificado no CI do PR #77 no merge ref `4139b0696fe1e378d80fccb8541e6232b91d01b5`: **576 passed, 5 warnings, 57.44s**.
- A tarefa não adicionou testes de runtime porque o pedido exige explicitamente nenhum código de runtime e nenhum teste funcional novo.

**Ficou pendente / virou backlog:**
- Tarefa 1 — Timeout, retry e escada de modelos com cooldown — é a próxima tarefa técnica.
- Tarefas 2–10 permanecem backlog/documentação de planejamento.
- A execução manual L4/L5 do runner live continua sendo obrigação da fase Browser Intelligence, conforme o estado oficial; esta tarefa não mexeu no Browser.

**Próxima tarefa:** 1
