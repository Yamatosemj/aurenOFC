# Nota de passagem — Auren V48

Tarefa concluída: 5 — Memória: núcleo no prompt, índice de chaves, painel e resumo de sessão

Arquivos criados/alterados:
- memory/store.py
- core/memory_context.py
- core/session.py
- tools/memory.py
- core/tools_registry.py
- core/tool_contracts.py
- tools/dispatcher.py
- core/router.py
- core/harness.py
- core/prompt.py
- config.py
- auren.py
- README.md
- AUREN_STATE.md
- tests/test_memory_v48.py
- docs/NOTAS_DE_PASSAGEM.md

Decisões tomadas (e por quê):
- SQLite foi mantido como persistência única.
- O contexto agora separa núcleo de 900 caracteres e índice de 420 caracteres.
- O núcleo e o índice percorrem categorias de forma intercalada, evitando que uma categoria muito grande monopolize o orçamento.
- listar_memoria usa o registry, contrato, Router, Dispatcher, permissão e ToolResult já existentes.
- O resumo pendente da sessão é um único registro SQLite, gravado no encerramento e consumido atomicamente na primeira montagem de contexto seguinte.
- O resumo é gerado somente a partir de turnos do usuário; respostas do assistente e resultados de ferramentas não entram nessa persistência.
- A leitura e a listagem também reaplicam o filtro existente contra dados de credenciais, protegendo bancos antigos.
- O limite de segurança de 5000 memórias não apaga entradas existentes; ao atingir o teto, novas chaves são rejeitadas e um aviso vai para o log.
- Não houve alteração de Browser ou Windows nesta tarefa.

Testes: (comando, nº de testes antes e depois, resultado)
- Comando exigido: py -m pytest -q
- Foram adicionados 11 testes específicos de memória/sessão.
- A contagem total antes e depois depende da execução do CI, pois o repositório não está montado localmente neste ambiente.
- Resultado final deve ser registrado aqui após o CI verde.
- Testes novos cobrem: orçamento/índice, intercalamento, consulta por chave/valor, registry/contrato, listagem e data, consumo único de sessão, isolamento de texto do assistente, filtro de credenciais, limite de segurança e preservação do valor persistido.
- Runner live Windows: não executado, pois nenhuma ferramenta Browser/Windows foi alterada.

Ficou pendente / virou backlog:
- Nenhuma pendência de teste conhecida.
- Painel visual da memória fica para a Tarefa 6.
- Validação live final do Browser Intelligence permanece no backlog.

Próxima tarefa: 6
