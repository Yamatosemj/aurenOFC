# Nota de passagem — Tarefa 8

Tarefa concluída: 8 — Carregador de plugins que passa pelo Dispatcher

Arquivos criados/alterados:
- `core/plugin_loader.py`
- `core/capabilities.py`
- `core/tool_contracts.py`
- `core/permission_manager.py`
- `tools/dispatcher.py`
- `core/prompt.py`
- `core/orchestrator.py`
- `providers/openai_provider.py`
- `auren.py`
- `config.py`
- `.gitignore`
- `README.md`
- `AUREN_STATE.md`
- `.github/workflows/auren-file-intelligence.yml`
- `.github/workflows/auren-visual-interaction.yml`
- `plugins/_template.py`
- `plugins/hora_atual.py`
- `plugins_aprovados.example.json`
- `tests/test_plugin_loader.py`
- `tests/test_execution_single_path.py`

Decisões tomadas (e por quê):
- O plugin entra nos registries de tools, contratos, capacidades e Dispatcher; não existe executor paralelo.
- O plugin novo começa em CONFIRM e só vira AUTO quando aprovado em `plugins_aprovados.json`; a capacidade não pode declarar sua própria política.
- Plugins desativados são filtrados antes do import e antes de `find_spec`.
- Dependências declaradas são verificadas com `importlib.util.find_spec`; ausência de módulo do próprio Auren gera diagnóstico do projeto e não sugestão de `pip install core`.
- Falhas de plugin, colisões e nomes inválidos são isoladas com motivo legível e não derrubam o boot.
- O retorno de plugin é marcado como conteúdo não confiável e passa pela mesma guarda do PermissionManager usada para conteúdo externo.
- O prompt final é gerado a partir do registry atual de capacidades; o texto-base continua sendo mantido como política fixa.
- O Router não foi alterado nesta tarefa: a tentativa de integrá-lo diretamente extrapolou o escopo e foi removida. A seleção continua tendo um único dono; o plugin só ganha execução por meio do Dispatcher.
- `hora_atual` e `plugins/_template.py` demonstram o formato sem exigir edição adicional do runtime para cada novo plugin.
- Nenhuma dependência nova foi adicionada.

Testes:
- Comando exigido: `py -m pytest -q`
- Baseline antes da tarefa: 438 passed, 6 skipped
- Resultado no head da implementação: 457 passed, 6 skipped
- Ganho: +19 testes passando
- CI full pytest verde no head `b7358f295239c668d65e38803462deaf35389351`
- Workflow focado visual continuou separado; nenhuma alteração de Browser/Windows exigiu o runner live desta tarefa.

Ficou pendente / virou backlog:
- Execução manual do runner Browser Intelligence em Windows continua pendente da fase anterior.
- Integração de capacidades de plugin em regras específicas do Router ficou fora da Tarefa 8 e não foi implementada silenciosamente.
- PR #81 permanece aberto para revisão; a tarefa passou o portão de testes.

Próxima tarefa: 9
