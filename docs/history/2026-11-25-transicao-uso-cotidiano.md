# Decisão de desenvolvimento — transição para uso cotidiano (25/11/2026)

## Escopo e evidências

Decisão acordada com o proprietário: (1) registrar as pendências anteriores; (2) encerrar o ciclo de implementação, mantendo a validação pendente; (3) revisar controle de mídia existente; (4) entregar o comando falado "Auren, pausa a música" de ponta a ponta; (5) expandir somente a partir dessa experiência funcional.

Base verificada: [main em 8158bf2](https://github.com/Yamatosemj/aurenOFC/commit/8158bf2c5add23508026ccb235d1854ace9c1e32). Este registro não altera runtime, permissões nem runner.

## Ciclo anterior — implementação encerrada, validação Live aberta

| Escopo | Implementação integrada | Evidência |
| --- | --- | --- |
| Etapas 1–2: continuidade e retomada de tarefa, preservando limites | Sim | [#180](https://github.com/Yamatosemj/aurenOFC/pull/180) |
| Etapa 3: obrigações de tarefas compostas | Sim | [#182](https://github.com/Yamatosemj/aurenOFC/pull/182) |
| Etapa 4: verificar destino técnico real | Sim | [#183](https://github.com/Yamatosemj/aurenOFC/pull/183) |
| Etapa 5: bloqueios externos e retomada segura | Sim | [#184](https://github.com/Yamatosemj/aurenOFC/pull/184) |
| Correção complementar: evidências de links, seleção e falha controlada | Sim | [#185](https://github.com/Yamatosemj/aurenOFC/pull/185) |

No SHA integrado, [CI completo Linux](https://github.com/Yamatosemj/aurenOFC/actions/runs/44634213700) aprovou 931 testes, 31 ignorados; [CI focado Linux/Windows](https://github.com/Yamatosemj/aurenOFC/actions/runs/44634213730) concluiu todos os jobs com sucesso. Contagens detalhadas na #185. Nenhum teste Live pós-merge é comprovado por esses runs.

## Pendências preservadas

| Pendência | Impacto/prioridade | Condição de encerramento |
| --- | --- | --- |
| Validar continuidade após esclarecimento, limites, cancelamento e troca de objetivo em situações reais | Bloqueante se reproduzir falha no caminho compartilhado | Evidência Live autorizada: mesma tarefa quando pertinente, novo objetivo quando explícito, sem reaproveitar autorização |
| Reproduzir pesquisa → abrir resultado e inconsistências entre contexto de aba/leitura/links após #185 | Não bloqueia mídia; bloqueia declarar navegação validada | Teste real pós-merge com link observado, seleção correta e URL ativa confirmada; registrar SHA e resultado |
| Bloqueio antibot/CAPTCHA e retomada | Não bloqueia mídia | Validar WAITING, intervenção humana, nova leitura e destino comprovado; falhar sem falsos sucessos se não houver evidência |
| Pedido de nova tentativa: continuidade ou nova tarefa conforme semântica | A confirmar; bloqueante se afetar núcleo | Reproduzir caso e definir comportamento conforme intenção; não afirmar regressão comprovada sem log |
| Pesquisa alternativa ao Google | Ideia não aprovada para implementação | Retomar apenas mediante decisão explícita; não contornar CAPTCHA |
| WAITING não persiste após reinício; relevância semântica, cobertura de desafios não observados | Limites conhecidos | Não elevar garantia além do código e testes; avaliar quando houver necessidade |

O teste Live de 19/11 relatado na #185 confirmou WAITING/retomada após "pronto", mas cinco propostas foram rejeitadas com result_precontext_missing e a tarefa terminou em model_round_limit sem abrir resultado. A #185 corrigiu causas reproduzidas offline; o log truncado não permite atribuir cada rejeição a uma causa específica. Outras PRs abertas e débitos históricos continuam pendentes de triagem, sem autorização de merge.

## Próximo ciclo — primeira utilidade cotidiana

Revisão estática inicial:
- [tools/windows_input.py](../../tools/windows_input.py): controle_midia_windows envia teclas globais; pausar e reproduzir convergem para play_pause. Não observa o estado nem garante qual sessão recebeu a tecla.
- [tools/windows_audio.py](../../tools/windows_audio.py): leitura e alteração de volume/mudo por Core Audio/COM; não é controle do estado de reprodução.
- [core/tools_registry.py](../../core/tools_registry.py): contrato atual de mídia aceita play_pause, proxima, anterior e parar.
- [tools/fast_paths.py](../../tools/fast_paths.py): fast path comum não executa mídia/volume/mudo localmente; [core/capability_audio_runtime.py](../../core/capability_audio_runtime.py) oferece experimento opt-in, não uma rota nova a duplicar. Revisar fallback após falha para impedir repetição de ação de efeito incerto.
- [voice/main.py](../../voice/main.py): PTT ativo via Ctrl direito + Shift direito; wake word não está no caminho ativo, conforme [arquitetura de voz](../architecture/06-voz-stt-tts.md). Ativação pelo nome exige implementação e validação próprias.

Ordem de entrega: testar o comportamento existente por texto/PTT com autorização; corrigir semântica de pausa (não alternar se já pausado), alvo e confirmação real; integrar ativação pelo nome de modo opt-in, com indicação/desligamento do microfone, proteção contra autoativação e preservação da autorização; validar frase completa no Windows; só então expandir para outras ações.

Critérios de aceitação da primeira utilidade: falar "Auren, pausa a música" sem teclado, reconhecer e executar pelo caminho único Router/Dispatcher/contrato/permissão/ToolResult; pausar a sessão pretendida, repetir sem retomar, lidar com ausência/ambiguidade de sessão sem sucesso falso, verificar estado final, medir latência ponta a ponta e confirmar que a captura não reage à própria saída. Registrar casos, ambiente, SHA, logs sem conteúdo sensível, falhas e latência observada. Testes unitários/CI não substituem esse teste físico. Sem meta arbitrária de latência ou mudança de arquitetura antes das medições. Nenhuma execução Live/API ou mudança no runtime neste registro.

Expansão (retomar, faixas, volume, inicialização, outros comandos) somente após a primeira experiência validada e nova decisão de escopo. Se aparecer defeito bloqueante no núcleo, corrigir em PR focalizada antes de prosseguir.