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
- Comando solicitado: py -m pytest -q
- CI executou: python -m pytest -q
- Full pytest Linux: 589 passed, 6 skipped, 5 warnings
- Full pytest Windows: 595 passed, 5 warnings
- Static checks: verdes
- Visual/focused CI: verde
- O checkout local não estava disponível por falha de DNS; por isso o resultado de validação foi obtido pelo CI do GitHub, não por uma execução local simulada.

Ficou pendente / virou backlog:
- A execução live `python testes_auren_live.py --rapido` não se aplica: esta tarefa não mexe em Browser/Windows.
- Tarefa 2 — memória recuperável sob demanda — passa a ser a próxima tarefa.


Proxima tarefa: 2

---

## 2026-10-07 — Tarefa 2 — Pilha de undo + primeiras ações reversíveis (volume e mudo)

Tarefa concluída: implementação e CI concluídos; portão de saída ainda pendente apenas pela execução manual do runner live no Windows real

Arquivos criados/alterados:
- core/undo.py
- tools/undo.py
- tools/windows_audio.py
- tools/dispatcher.py
- core/tools_registry.py
- core/tool_contracts.py
- core/capabilities.py
- core/intent_resolver.py
- core/permission_manager.py
- core/router.py
- tests/test_router_tool_selection.py
- tests/test_undo.py
- tests/test_tool_contracts.py
- tests/test_dispatcher_contracts.py
- tests/test_capability_registry.py
- AUREN_STATE.md
- docs/NOTAS_DE_PASSAGEM.md

Decisões tomadas (e por quê):
- A pilha usa RLock e mantém no máximo 10 entradas, em ordem LIFO.
- O horário é armazenado como datetime UTC com timezone para que cada entrada tenha marca temporal real e não dependa de relógio monotônico exposto ao usuário.
- A entrada de undo só é removida depois de o callback confirmar sucesso. Em falha, permanece no topo e o ToolResult informa error_code estruturado; isso evita perda silenciosa da única forma conhecida de reversão.
- Volume e mudo usam helpers privados para aplicar o estado sem registrar outro undo durante a própria reversão.
- Ausência ou falha de leitura do estado anterior não impede a ação solicitada, mas impede o registro do undo.
- desfazer_ultima_acao foi ligado ao Router, registry, contrato, capability, permissão e Dispatcher, mantendo o fluxo único do Auren.
- O Mark-LV foi usado somente como referência de comportamento e casos-limite; nenhum código ou comentário foi copiado.

Testes:
- Baseline conhecido antes: py -m pytest -q = 576 passed, 5 warnings
- Novos testes/asserções nesta tarefa: 15
- Comando exigido: py -m pytest -q
- Execução local completa: não disponível neste ambiente; não havia checkout local utilizável
- GitHub Actions no head 119bf4fe01408580f15710f9cf63300f45c8c2bd: full pytest Linux 605 passed, 6 skipped, 5 warnings; full pytest Windows 611 passed, 5 warnings; static-checks e visual interaction verdes
- Runner manual python testes_auren_live.py --rapido: não executado, porque este ambiente não é o Windows real do Auren

Ficou pendente / virou backlog:
- Fechar o portão com py -m pytest -q verde e quantitativo final de testes
- Executar python testes_auren_live.py --rapido no Windows real
- Só então promover V48 de em validação para estável
- Memória recuperável sob demanda continua pendente e foi preservada no backlog; ela não foi falsamente declarada concluída

Próxima tarefa: 4 — confirmação humana não-forjável, após a validação final do undo
---

## 2026-10-07 — Tarefa 3 — Operações de arquivo seguras com undo e Lixeira

Tarefa concluída: implementação da Tarefa 3; portão de saída ainda pendente da execução final do pytest no CI e do runner live no Windows real

Arquivos criados/alterados:
- tools/file_intelligence.py
- tools/files.py
- tools/dispatcher.py
- core/tools_registry.py
- core/tool_contracts.py
- core/capabilities.py
- core/permission_manager.py
- tests/test_file_intelligence.py
- tests/test_permission_policy.py
- tests/test_capability_registry.py
- tests/test_router_tool_selection.py
- tests/test_tool_contracts.py
- tests/test_dispatcher_contracts.py
- README.md
- AUREN_STATE.md
- docs/NOTAS_DE_PASSAGEM.md

Decisões tomadas (e por quê):
- Reaproveitar a política de caminhos já usada pela inteligência de arquivos, mas transformar qualquer caminho de mutação fora da allowlist em BLOCKED, sem confirmação que possa abrir uma escrita fora das pastas autorizadas.
- Bloquear symlink, junction e demais reparse points presentes no caminho antes de resolver o alvo.
- Destino existente gera `destination_exists`; não usamos sufixo `(1)` porque erro explícito é mais previsível para uma ação comandada por voz.
- Mover, copiar, renomear e criar pasta registram undo. A reversão usa SHA-256 para evitar reaplicar a operação sobre conteúdo que mudou.
- Undo de cópia remove somente a cópia criada pelo Auren e só quando o SHA-256 permanece igual; criação de pasta só é desfeita quando a pasta continua vazia.
- Lixeira usa somente a Shell API nativa `SHFileOperationW` com `FOF_ALLOWUNDO`; nenhuma dependência nova foi adicionada e nenhuma exclusão permanente é exposta como ferramenta.
- Não registramos undo da Lixeira porque não há uma restauração confiável implementada nesta tarefa.
- O fluxo permanece Router → Dispatcher → Contrato → Permissão → Ferramenta → ToolResult.

Testes:
- Baseline imediatamente anterior: Linux 605 passed, 6 skipped, 5 warnings; Windows 611 passed, 5 warnings.
- Novos testes desta tarefa: 17.
- Comando exigido: `py -m pytest -q`.
- Validação automatizada esperada após os 17 testes novos: Linux 622 passed / 6 skipped; Windows 628 passed, antes do resultado real do CI.
- Execução local completa não disponível neste ambiente; não foi criado um resultado de teste falso.
- Runner manual `python testes_auren_live.py --rapido`: pendente no Windows real, como exige o portão da tarefa.

Ficou pendente / virou backlog:
- Fechar o CI final do PR #78.
- Executar `python testes_auren_live.py --rapido` no Windows real do Auren.
- Só depois promover V49 de “em validação” para estável.
- Tarefa 4 — confirmação humana não-forjável continua sendo a próxima frente do roadmap.

Próxima tarefa: 4 — confirmação humana não-forjável, após o portão da Tarefa 3


---

## 2026-10-07 — Tarefa 4 — Política reversível/irreversível e confirmação com timeout

Tarefa concluída: implementação da infraestrutura de confirmação; política de risco aprovada sem reclassificação de clipboard

Arquivos criados/alterados:
- core/confirmation.py
- voice/confirmation.py
- voice/main.py
- tests/test_confirmation.py
- tests/test_permission_policy.py
- docs/POLITICA_DE_CONFIRMACAO.md
- AUREN_STATE.md
- docs/NOTAS_DE_PASSAGEM.md

Decisões tomadas (e por quê):
- O Undo existente da linha V49 foi auditado antes de qualquer promoção para AUTO. Arquivos e volume/mudo possuem restauração condicionada ao estado observado; memória e clipboard não possuem restauração exata.
- memory.write permanece CONFIRM porque esquecer uma memória atualizada não recupera o valor/categoria/timestamp anteriores.
- windows.clipboard.write recebeu proposta AUTO → CONFIRM, mas o usuário decidiu explicitamente manter AUTO. O PermissionManager já estava em AUTO e não sofreu reclassificação.
- ConfirmationRequest não carrega token. O token é criado e mantido pela interface, fica fora dos argumentos do modelo e é aceito pelo gate apenas durante a janela válida.
- Há uma única confirmação pendente por processo nos canais padrão; tokens atrasados ou inválidos não cancelam uma confirmação nova.
- Timeout padrão: 90 s. Expiração sempre significa negativa e não executa a ação.
- Texto e voz continuam implementando o mesmo ConfirmationChannel; o canal de voz usa o timeout oficial.
- Foi adicionada uma regressão que exige que toda capability registrada tenha nível explícito no PermissionManager e rejeita o fallback generic.
- A política completa das 28 capabilities está documentada em docs/POLITICA_DE_CONFIRMACAO.md.
- O Mark-LV foi usado somente como referência de arquitetura/risco e casos-limite; nenhum código ou comentário foi copiado.

Testes:
- Baseline imediatamente anterior: Linux 622 passed / 6 skipped, conforme registro da Tarefa 3; Windows 628 passed, conforme registro da Tarefa 3.
- Novos testes da Tarefa 4: 4 testes.
- CI head 8da961772abccac15ec7a6090293128469ae02aa: static-checks e Playwright smoke verdes; full pytest Linux = 624 passed, 6 skipped, 4 failed; full pytest Windows = 630 passed, 4 failed. Os 5 testes adicionados pela Tarefa 4 passaram.
- Execução local completa não disponível por ausência de DNS/rede neste ambiente; nenhum resultado local foi inventado.
- Runner manual python testes_auren_live.py --rapido: pendente no Windows real, porque esta tarefa altera a confirmação usada pelo canal de voz e o ambiente atual não é o computador do Auren.

Ficou pendente / virou backlog:
- Registrar a decisão: windows.clipboard.write permanece AUTO por escolha explícita do usuário.
- Registrar que o portão geral não fecha enquanto as 4 falhas preexistentes da V49 permanecerem. Elas já existiam no head V49 anterior, que tinha Linux = 619 passed, 6 skipped, 4 failed e Windows = 625 passed, 4 failed.
- Executar o runner live no Windows real antes de considerar o portão externo encerrado.

Próxima tarefa:
- Concluir o fechamento documental da Tarefa 4 sem reclassificação de clipboard e seguir para o próximo passo somente após o portão.


Atualização do fechamento da evidência:
- As quatro falhas não envolvem os novos testes de confirmação. O full pytest da Tarefa 4 aprovou todos os cinco testes adicionados.
- As mesmas quatro falhas foram reproduzidas no head V49 anterior d19ebf511d5d35623e187436c432b057a76428c5, antes das alterações de confirmação.
- Portanto, elas permanecem como débito da Tarefa 3 e não foram corrigidas nesta tarefa para respeitar a regra de uma tarefa por vez.
