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


## 2026-10-07 — Tarefa 10A — Lembretes persistentes

Tarefa em validação: 10A — Lembretes

Arquivos criados/alterados nesta transição:
- `tools/reminders.py`
- `core/tools_registry.py`
- `core/tool_contracts.py`
- `core/capabilities.py`
- `core/permission_manager.py`
- `core/router.py`
- `tools/dispatcher.py`
- `core/facade.py`
- `auren.py`
- `config.py`
- `README.md`
- `AUREN_STATE.md`
- `tests/test_reminders.py`
- `tests/test_tool_contracts.py`
- `tests/test_dispatcher_contracts.py`

Decisoes tomadas:
- As tres tools usam o caminho existente `Router -> Dispatcher -> Contrato -> Permissao -> Ferramenta -> ToolResult`; nao existe executor paralelo de lembretes.
- `criar_lembrete` fica em CONFIRM porque cria estado persistente no Windows.
- `listar_lembretes` fica em AUTO porque somente consulta metadata e a existencia das tarefas.
- `cancelar_lembrete` fica em CONFIRM e e a reversao natural da criacao.
- O Agendador de Tarefas do Windows recebe uma tarefa ONCE via XML. O horario fica no `StartBoundary` em formato ISO local, evitando parsing de data dependente de localizacao.
- A acao do scheduler recebe o executavel Python e os argumentos como campos separados; no runtime do Auren nao ha `shell=True`.
- O agendamento chama somente `tools.reminders --disparar <id>`; a mensagem fica no armazenamento local e nao e interpolada na linha de comando ou no XML.
- O nome da tarefa e derivado exclusivamente do ID validado. Metadata local nao pode trocar o alvo do cancelamento para outra tarefa.
- A metadata e gravada em `%APPDATA%\\Auren\\lembretes.json`. A criacao desfaz a escrita da metadata quando o scheduler falha.
- O runner e de ocorrencia unica: depois de uma notificacao bem-sucedida, a tarefa e removida e a metadata do lembrete e apagada.
- Nenhuma dependencia externa foi adicionada.
- O nome `actions/reminder.py` do enunciado foi tratado como referencia de design; esse arquivo nao existia no Auren e a implementacao foi escrita de novo em `tools/reminders.py`.

Testes novos:
- registry/contrato das tres tools
- politica CONFIRM/AUTO
- selecao do Router
- criacao e rollback com scheduler simulado
- listagem e limpeza de tarefas obsoletas
- cancelamento
- XML do Task Scheduler
- garantia de comando por lista e ausencia de shell
- caminho unico via Dispatcher
- runner de disparo

Comando exigido:
`py -m pytest -q`

Baseline antes desta tarefa:
- 457 passed, 6 skipped

Portão pendente:
- CI completo do PR #82 precisa ficar verde
- `python testes_auren_live.py --rapido` em Windows deve ser executado após a funcionalidade estar disponível no ambiente real; este ambiente não tem Windows para executar esse runner

PR:
- #82 — Tarefa 10A
- empilhada sobre #81; quando #81 entrar na main, o diff da #82 passa a representar apenas a Tarefa 10A

Próximo passo após o portão:
- Tarefa 10B — Pesquisa na web em modos
