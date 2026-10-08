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
- O nível inicial é CONFIRM e a promoção para AUTO depende de `plugins_aprovados.json`; o plugin não declara sua própria política.
- Plugins desativados são filtrados por AST antes de import e não têm dependências consultadas.
- Dependências declaradas são verificadas com `find_spec` antes do import; módulos do próprio Auren ausentes recebem diagnóstico de projeto incompleto, não instrução de `pip install core`.
- O retorno de plugin é marcado como conteúdo não confiável e alimenta a mesma guarda de confirmação usada para leituras externas.
- O prompt final é gerado a partir do registry de capacidades em tempo de uso, sem abandonar o texto-base de segurança.
- `hora_atual` é o exemplo oficial e funciona pelo Dispatcher sem edição adicional do runtime.
- Nenhuma dependência nova foi adicionada.

Testes: `py -m pytest -q`; baseline conhecido do CI antes da tarefa: 438 passando; resultado final: pendente enquanto o PR #81 termina o CI.

Ficou pendente / virou backlog:
- Execução manual do runner Browser Intelligence em Windows continua pendente da fase anterior.
- Nenhuma nova integração ou feature fora da tarefa 8 foi implementada.

Próxima tarefa: 9
