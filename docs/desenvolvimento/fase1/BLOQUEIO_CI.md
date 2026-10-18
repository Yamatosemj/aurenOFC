# Bloqueio do ciclo: encerramento de processos no Windows

Em 18/10/2026, o CI da Fase 1 no código `6f220aab9bf6a0a5aee4488daa0cd6e170c1f144` falhou. A implementação da persistência está salva, mas a fase **não está aprovada** e a Fase 2 não foi iniciada.

Evidência: [execução 39101893307](https://github.com/Yamatosemj/aurenOFC/actions/runs/39101893307).

| Ambiente | Aprovados | Falhas | Ignorados |
| --- | ---: | ---: | ---: |
| Windows local, perfil fictício | 1005 | 0 | 8 |
| Windows hospedado no GitHub | 1012 | 1 | 0 |
| Linux hospedado no GitHub | 972 | 0 | 41 |

A falha foi `tests/test_remote_live_safety.py::test_idle_timeout_kills_child_and_grandchild`. O supervisor retornou `idle_timeout`, código 124, mas a consulta imediata ao processo descendente ainda indicou que estava ativo. O teste utiliza somente processos Python fictícios; não houve teste do Auren com API, programas pessoais ou dispositivos.

## Investigação e limite da conclusão

O código atual chama `TerminateJobObject`, consulta `BasicAccounting.ActiveProcesses` até chegar a zero e aguarda o processo principal. Não aguarda individualmente os identificadores dos descendentes. O resultado hospedado demonstra que a garantia observada pelo teste ainda não foi atendida; não comprova sozinho a causa exata. Permanecem hipóteses a distinguir com evidência: intervalo entre contabilização e sinalização final dos processos, comportamento do ambiente hospedado ou reutilização do PID consultado pelo teste. Não declarar nenhuma dessas hipóteses como causa confirmada.

O mesmo teste já tinha falhado na Fase 0, motivando o ajuste documentado em [SUPERVISOR_WINDOWS.md](../fase0/SUPERVISOR_WINDOWS.md). O CI final daquela fase passou, mas a recorrência invalida tratar esse resultado isolado como prova de resolução duradoura. Não foi alterado o teste, aumentado seu tempo, removida a verificação ou repetido o CI até obter verde.

## Motivo da interrupção e retomada

O proprietário determinou interromper a sequência diante de risco de segurança ou bloqueio persistente. Encerramento não comprovado de descendentes é um limite de segurança dos testes. Portanto, a Fase 1 fica bloqueada, com PR de rascunho, e as Fases 2 a 5 ficam pendentes. Nenhuma branch foi mesclada e a main não foi modificada.

Próximo trabalho técnico: reproduzir o caso com evidência da identidade e do estado dos processos, verificar a semântica das APIs do Windows em documentação primária e corrigir a causa antes de retomar o ciclo. Preservar kill-on-close, limites, ausência de breakaway e a verificação independente de término; nunca encerrar por nome nem atingir processos preexistentes. Não instalar o supervisor candidato no runner pessoal. Depois da correção, executar o teste de falha, os testes de contenção e a suíte completa nos dois sistemas no SHA final.

Não foram testados nesta fase: uso com modelo/API reais, execução continuada de objetivos, interface de retomada, rotinas proativas, dispositivos, dados pessoais ou ações sensíveis. Não há orçamento definido para testes pagos.
