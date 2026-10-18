# F0-SEG-002 — confirmar o encerramento dos descendentes

Na conferência do HEAD documental `da85b5e`, o [CI completo 39099859051](https://github.com/Yamatosemj/aurenOFC/actions/runs/39099859051) falhou no Windows: `test_idle_timeout_kills_child_and_grandchild` observou o processo descendente ainda ativo depois do retorno do supervisor. Resultado: 981 aprovados e uma falha; Linux: 942 aprovados e 40 ignorados. A Fase 1 não foi iniciada com esse resultado.

O supervisor solicitava o encerramento do Job Object e esperava somente o processo principal. Isso não comprovava o término dos descendentes no instante do retorno. A [documentação Microsoft de TerminateJobObject](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-terminatejobobject) relaciona a operação a TerminateProcess, cujo [encerramento é assíncrono](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-terminateprocess). A falha não demonstra que o descendente permaneceria vivo indefinidamente; demonstra que o supervisor retornava antes da comprovação exigida pelo teste.

Foram escritas três reproduções determinísticas antes da correção: encerramento que ainda tem processos ativos, prazo esgotado e falha ao consultar o estado. As três falharam no código anterior. A primeira tentativa passou a consultar o Job, mas retirou a espera pelo processo principal; dois testes reais de processos falharam. A segunda preservou também essa espera. Nenhum teste anterior foi removido, relaxado ou marcado como falha esperada.

A correção mantém o Job Object e seus limites, nega breakaway, preserva kill-on-close e consulta [ActiveProcesses](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_accounting_information) até chegar a zero, com prazo de cinco segundos. A conferência é feita também quando o principal sai normalmente, para não deixar descendentes órfãos. Continua esperando o handle do principal; se a consulta ou a espera não confirmar o encerramento, retorna `cleanup_failed`, código 125, em vez de sucesso. Não há encerramento por nome de aplicativo ou busca global de PIDs.

Foi acrescentado um teste de falha de confirmação da limpeza: a fixture é encerrada de verdade, a falha é injetada depois, e o supervisor precisa devolver código de erro. Os demais testes reais usam somente processos Python fictícios criados pelos próprios testes. Não são testes Live do Auren, não executam aplicativos pessoais e não usam API ou dispositivos.

Validação local isolada:

| Execução | Passaram | Falharam | Ignorados |
| --- | ---: | ---: | ---: |
| Reproduções antes da correção | 0 | 3 | 0 |
| Primeira tentativa, seleção focada | 13 | 2 | 0 |
| Segunda tentativa, seleção focada | 15 | 0 | 0 |
| Suíte completa, incluindo novo controle de limpeza | 978 | 0 | 8 |

Suíte completa: 49,32 segundos, Windows/Python 3.13.15, dados e perfil temporários, credenciais removidas. Os oito ignorados exigem links simbólicos indisponíveis localmente. Artefatos e hashes em `RESULTADOS_SUPERVISOR.json`. Os testes focados se sobrepõem à suíte completa; não somar.

Esta é uma mudança no arquivo versionado `remote_tests/windows_watchdog.py`. Nenhum controlador fixado, hook pessoal, aprovação, política local, workflow ou instalação do runner foi alterado. O runner confiável já instalado não recebe esta correção automaticamente; eventual atualização exige seu processo próprio de revisão. O CI final do novo HEAD deve ser registrado na PR #154 antes do avanço. A existência desta correção não constitui autorização para executar Live no PC.
