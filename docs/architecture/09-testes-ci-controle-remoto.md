# Arquitetura 09 — Testes, CI, runner Windows e controle remoto

> **Etapa 9 — auditoria estática** da `main` em `1bb85bc04efe850cd0705652c54e5cddcee9a8bd` (2026-10-10), cotejada com os workflows, testes, documentação histórica e runs concretos do GitHub. **Não foi iniciado nenhum teste no Windows pessoal nesta PR.** Executar pytest no runner hospedado, testar o próprio Windows via self-hosted e acionar API/desktop Live são operações diferentes.
>
> Guias de operação: [Testes GitHub](../TESTES_GITHUB.md) e [Controle remoto GitHub](../CONTROLE_REMOTO_GITHUB.md). Regras de execução: [AGENTS.md](../../AGENTS.md). Para cancelamento/Harness, consulte [01](01-nucleo.md); para permissões das tools, [02](02-roteamento-seguranca.md).

## 1. Quais testes existem — e o que cada um prova

| Categoria | Gatilho / ambiente | Escopo e cautela |
| --- | --- | --- |
| **CI da PR: suíte completa** | [`auren-file-intelligence.yml`](../../.github/workflows/auren-file-intelligence.yml), `pull_request` ou `push` em `main`; `ubuntu-latest`, Python 3.13 | `python -m pytest -q` coleta apenas `tests/` ([`pytest.ini`](../../pytest.ini)). Regressão automatizada no GitHub, **não** teste no PC do proprietário |
| **CI da PR: focados/safe** | [`auren-visual-interaction.yml`](../../.github/workflows/auren-visual-interaction.yml), Linux **e** `windows-latest` hospedados | Bateria selecionada de Router, contrato, visão, confirmação, arquivos, GUI, política remota etc.; bloco com `AUREN_TEST_MODE=1` nega confirmação interativa. **Windows hospedado não é o Windows pessoal** |
| **Pytest manual hospedado** | [`auren-manual-tests.yml`](../../.github/workflows/auren-manual-tests.yml), `workflow_dispatch`; matriz Ubuntu/Windows | Roda `tests` com JUnit, log, dependências e sumarização; retenção de artifacts por **14 dias**; não é Live nem self-hosted |
| **Conexão do runner pessoal** | [`auren-windows-connection.yml`](../../.github/workflows/auren-windows-connection.yml), `workflow_dispatch` autorizado em `main` | Confirma chegada de job a runner `self-hosted/Windows/X64/auren-isolated`, sem importar Auren; não comprova testes funcionais |
| **Windows pessoal — Live** | [`auren-windows-live.yml`](../../.github/workflows/auren-windows-live.yml), `workflow_dispatch` do proprietário com SHA revisado | Pode causar efeitos no desktop e, em L4/L5, consumir API. Requer aprovações, ambiente e política **local**; **não** é o CI de PR |
| **Controle remoto manual de PR / atualização** | [`auren-update-pc.yml`](../../.github/workflows/auren-update-pc.yml), `workflow_dispatch` sobre `ci/remote-update-control` | `testar_pr` testa checkout separado sob watchdog; `atualizar_main` usa `git pull --ff-only` no clone principal, sem reset |
| **Teste por comentário na PR** | [`auren-chat-tests.yml`](../../.github/workflows/auren-chat-tests.yml), evento `issue_comment`, próprio dono | Aceita **somente** `AUREN_TESTE_V1 pytest <SHA40>` de PR aberta e interna. Validação hospedada + execução pytest no runner pessoal, **sem chave API**; não autoriza Live |
| **Runner manual do Auren** | [`testes_auren_live.py`](../../testes_auren_live.py), explicitamente ou sob watchdog | Baterias L0/L1/L2/L4/L5 e relatório `logs/testes/RESULTADO_TESTE_AUREN.txt`; **fora** da coleta pytest normal. [`testes_auren.py`](../../testes_auren.py) é fachada legada |

**Evidência recente:** a PR #128 passou [Linux completo](https://github.com/Yamatosemj/aurenOFC/actions/runs/38098004028) com **556 passed/24 skipped** e [focados Linux/Windows](https://github.com/Yamatosemj/aurenOFC/actions/runs/38098004152) com **166 passed/15 skipped** Linux, **181 passed** Windows hospedado e **110 passed** em modo seguro por sistema. Esses totais são **daquelas execuções**, não meta, garantia futura ou contagem obrigatória de todos os testes.

## 2. Fronteiras de segurança e diferença entre CI e Live

\`\`\`text
PR / push em main ──> GitHub-hosted Linux/Windows ──> pytest/mocks ──> status da PR
                                               (nenhum efeito no PC pessoal)

Comando explícito do dono ──> GitHub valida evento, SHA e PR
                            └─> runner Windows pessoal habilitado
                                └─> before-job.ps1 + aprovação local
                                    └─> watchdog/Job Object
                                        └─> checkout isolado da PR
                                            └─> pytest OU camada Live explicitamente aprovada
                                            └─> JSON/log/JUnit/artifacts privados
\`\`\`

As *labels* `auren-isolated` apenas selecionam o runner; **não fornecem sandbox**. O código da PR executado via pytest pode acessar recursos permitidos à conta Windows usada pelo runner, mesmo sem API. Uma conta sem admin, Job Object e timeout reduzem risco mas não tornam código arbitrário não confiável seguro. Verificar origem, alterações e SHA antes de testar código que não tenha sido revisado. A autorização de **um** teste de pytest não autoriza Live.

A política efetiva `before-job.ps1`, os arquivos de aprovação e o estado `STOP-LIVE` estão **no Windows, fora do repositório**. O conteúdo exato e o status atual desses arquivos **não são verificáveis apenas lendo GitHub**. Nunca desativar, atualizar ou substituir o hook para destravar job sem revisão/aprovação explícita do proprietário. Também não alterar secrets, permissões ou requisitos de ambiente para fazer checks verdes.

## 3. Teste pelo chat: fluxo efetivamente validado em 2026-10-10

1. Em uma **PR aberta, não draft, interna e com base `main`**, o proprietário publica exatamente `AUREN_TESTE_V1 pytest <SHA de 40 caracteres minúsculos>` como comentário. Não é comando em shell; texto livre, nomes de branch, camadas Live e strings extras são rejeitados.
2. O job hospedado `validar` carrega um [validador fixado](../../remote_tests/chat_request.py) no commit `b695fad7cc668d9a47e4dfc72f11a74b152d9cac`. Checa repo privado, autor/proprietário, tentativa original, comentário, PR aberta, origem interna e `head.sha` exato. O pedido não escolhe shell, scripts nem outro método.
3. O job `executar` requer ambiente `auren-windows` e runner Windows privado. Faz checkout do **controlador confiável e imutável** `448a1f87a672278471d1d8dcc08a2a621e10b77c` e de **outro** checkout da PR no SHA confirmado. Também confere SHA exato do controlador e da PR.
4. Remove `OPENAI_API_KEY` do ambiente do job, inicia [`remote_tests/pr_job.py`](../../remote_tests/pr_job.py) com `--camada pytest` e [`windows_watchdog.py`](../../remote_tests/windows_watchdog.py) com `AUREN_TEST_MODE=1`. A suíte usa diretório temporário em Downloads e gera `reports/pr-result.json`, `pr-test.log` e `pytest.xml`. Artifacts privados: **7 dias**.
5. A execução também depende da política **local** `before-job` com aprovação de blob/workflow e usuário não elevado. O [complemento local](../../remote_tests/chat-control-functions.ps1) é uma verificação *offline* de contexto/evento/workflow/SHA apresentado; ele **não consulta novamente a API para provar que a PR continua no mesmo SHA**. Confia no job hospedado e na integridade dos commits fixados.

### Evidência ponta a ponta já existente

- A [PR #119](https://github.com/Yamatosemj/aurenOFC/pull/119) recebeu comentário do proprietário: `AUREN_TESTE_V1 pytest 9fa20a4cb92dfead9a77fa9356d8677bcf559be8`.
- Na [execução #38085000162](https://github.com/Yamatosemj/aurenOFC/actions/runs/38085000162), **validar** e **executar** terminaram com `success`. Os logs do validador confirmam **PR #119 e o mesmo SHA**, e os logs do executor trazem `PR test: completed; exit=0`.
- Foi publicado o artifact privado `auren-chat-pr-119-38085000162` (retenção configurada para sete dias).

**Conclusão delimitada:** foi comprovado **um ciclo real de pedido por comentário → validação → job Windows → pytest bem-sucedido**, em 10 de outubro de 2026. Isso **corrige os avisos históricos de “ainda não operacional”** nos documentos antigos. **Não** atesta que o runner esteja online agora, que a política local permaneça idêntica, que toda futura PR rode automaticamente ou que testes com efeitos/API estejam liberados. Não foi enviado outro comentário/teste como parte desta auditoria.

## 4. Controle remoto manual do PC

O workflow [`auren-update-pc.yml`](../../.github/workflows/auren-update-pc.yml) é **manual** e condicionado a repo privado, dono como ator/reator e `refs/heads/ci/remote-update-control`. Exige permissão local correspondente e usa o mesmo runner com ambiente `auren-windows`. **Não** é acionado pelo comentário usado na seção 3.

- **`operacao=atualizar_main`:** lê um caminho de checkout explicitamente configurado no Windows, verifica Git, branch `main`, `origin` esperado e árvore rastreada sem alterações; executa `git pull --ff-only origin main`. Sem `reset --hard`, sem merge forçado e sem fazer o pull do clone de uma PR. Uma execução [#37890091132](https://github.com/Yamatosemj/aurenOFC/actions/runs/37890091132) terminou com ambos os jobs `validar`/`executar` aprovados; isso não prova o estado atual do clone.
- **`operacao=testar_pr`:** valida número, PR aberta/não draft/interna na `main` e congela o SHA no começo; usa `pr-checkout` separado e código de controle revisado. `camada=pytest` é o padrão; `L0/L1/L2` requerem acionamento explícito, `L4/L5/ALL` exigem também `sha_aprovado` igual ao SHA da PR e disponibilidade de API. **Não executado nesta auditoria**.

A branch de controle é intencionalmente mais estável que `main`; a condição no workflow impede tratá-las como intercambiáveis. Nesta revisão, os blobs versionados de `pr_job.py` e `windows_watchdog.py` na `main` coincidiram com o commit fixado do controlador, e o validador do chat também coincidiu com seu commit fixado. **Isso não verifica os arquivos de política no PC nem autoriza mudar SHAs pinados.**

## 5. Windows real e camadas do tester

[`testes_auren_live.py`](../../testes_auren_live.py) é um runner manual de **2.050 linhas** no snapshot desta revisão; a versão reportada por ele é `TEST_SUITE_VERSION=47`, build `V18-p0-3-bateria-fast-path-aware`. O `pytest.ini` não o coleta.

| Camada | Natureza |
| --- | --- |
| **L0** | Descoberta e pré-condições/compatibilidade estática |
| **L1** | Smoke e guardas controlados; pode operar sem API, mas resultados dependem do ambiente |
| **L2** | Operações e verificações adicionais em Windows real; **pode alterar estado** e precisa de proteção |
| **L3** | **Reservada**, o próprio runner avisa que não há testes L3 implementados |
| **L4** | Cenários representativos com modelo real; ações em desktop/navegador, API e efeitos possíveis |
| **L5** | Bateria Live maior/regressiva, também com modelo real e efeitos |

Sem `--camada`, o runner manual usa `L0,L1`; `--completo` usa `L0,L1,L2,L4,L5`. Escolher camadas maiores inclui automaticamente dependências inferiores. O workflow [`auren-windows-live.yml`](../../.github/workflows/auren-windows-live.yml) **não** oferece L3; fornece `L0`, `L1`, `L2`, `L4`, `L5`, `ALL` e opção separada `verificar_protecoes`. Exige variável `AUREN_WINDOWS_ENABLED`, SHA `AUREN_REVIEWED_SHA` igual ao da execução, aprovações do proprietário e política local. **Não equiparar a existência dessas opções à execução ou aprovação atual de todas as camadas.**

Os testes hospedados de segurança não importam/automatizam todas as ferramentas reais do Auren. O workflow Live pode solicitar API local existente e produz reports privados por sete dias. Uma execução histórica [#37885714287](https://github.com/Yamatosemj/aurenOFC/actions/runs/37885714287) validou o job de fixtures seguras; **não** use esse run para afirmar que todas as camadas Live passaram.

## 6. Supervisor Windows: limites reais e limitações

[`remote_tests/windows_watchdog.py`](../../remote_tests/windows_watchdog.py) cria processo inicialmente **suspenso**, atribui à **Windows Job Object** e só então o libera. Limites configurados:

- **1.200 s (20 min)** no máximo por suite e **120 s sem produção de saída**, log limitado a **16 MiB**; workflow GitHub limitado a **25 min**, com margem para upload.
- **64 processos** e **4 GiB** na árvore da Job Object; encerramento de filhos ao fechar o último handle, sem matar processos preexistentes por nome.
- Mutex `Local\\AurenAuthorizedLiveTests` impede duas baterias locais simultâneas; arquivo `%USERPROFILE%\\auren-remote\\STOP-LIVE` permite interrupção de emergência e bloqueia novas baterias quando presente.
- `AUREN_TEST_MODE=1` é propagado ao subprocesso; [testes de segurança](../../tests/test_remote_live_safety.py) incluem timeout, flood, herança de filho, cancelamento, stdin não interativo e redaction de chave fictícia.
- Segredos exibidos em stdout/log são um risco; o supervisor substitui a **string exata** de `OPENAI_API_KEY` no arquivo de log antes de reportá-lo, mas isso **não sanitiza todos os possíveis segredos ou dados pessoais**. Não publicar logs completos indiscriminadamente.

**Limites de promessa:** um Job Object controla a árvore **sob sua posse**, mas não reverte volume, clipboard, arquivos, navegador, janelas ou rede já alterados; não isola o perfil do usuário Windows. A ausência de saída por 120 s não mede progresso lógico (um loop que escreve constantemente continua até o limite absoluto). Erros de setup e falhas são preservados como resultado; **não** fingir que `success` da Action significa sucesso funcional de toda interação com o desktop.

## 7. Onde buscar evidência e como classificar resultados

| Fonte | Usar para |
| --- | --- |
| PR + **commit exato** | Escopo, alterações, code review, branch-base e SHA sob teste |
| Workflow run e **jobs** | Disparo, runner hospedado vs self-hosted, sucesso/falha, limites de job e histórico |
| Logs + relatório JUnit | Testes realmente coletados, passes/skips/falhas e motivo do encerramento |
| `pr-result.json` + `pr-test.log` | Resultado do watchdog de teste de PR, camada, `reason`, `exit_code`, duração |
| `reports/watchdog.json` + `reports/live.log` | Execução de Windows Live, watchdog e falhas; inspeção sempre limitada a relatório seguro |
| `logs/testes/RESULTADO_TESTE_AUREN.txt` | Bateria manual Live, camadas solicitadas e seus casos PASS/FAIL |
| Política local do PC | Estado efetivo de aprovação, emergência, usuário/serviço e permissões; **não inferir do GitHub** |

Retenção: chat/PR remoto e Live **7 dias**, pytest manual hospedado **14 dias**, conforme YAML. Os dois workflows automáticos de CI exibem logs próprios do GitHub. Não apresentar links para artifacts expirados como se os arquivos ainda estivessem disponíveis.

Em relatórios futuros, classificar separadamente: **(a)** código lido/auditado estaticamente, **(b)** teste unitário simulado, **(c)** CI Linux hospedado, **(d)** CI Windows hospedado, **(e)** pytest no runner Windows pessoal, **(f)** teste Live com hardware/API real, **(g)** sucesso de tarefa real no Auren. Uma categoria **não comprova** outra.

## 8. Riscos e pendências para tarefas independentes

1. **Documentação histórica atrasada:** as duas páginas de operação foram reconciliadas nesta PR quanto à existência de uma execução por comentário em 2026-10-10. Outros procedimentos de instalação e autorização continuam dependentes da política local e não devem ser reescritos sem evidência atual.
2. **Antes de cada novo teste remoto:** confirmar PR aberta e SHA atual, code review, conta proprietária, runner/política aprovados e camada correta; não assumir permissões do passado.
3. **Testes de comentários não significam Live:** o formato da mensagem só permite `pytest` sem API. Solicitações que exigem outra camada necessitam fluxo de despacho/aprovação separado.
4. **Fallbacks e credenciais:** revisar riscos de execução parcial, logs, ambiente e duplicação de efeitos antes de ampliar escopos; nunca contornar o hook Windows para simplificar o chat.
5. **Checks vermelhos ou sem runner:** diagnosticar em log/status da Action; não alterar workflow, antes-de-job, permissões, segredos nem SHA pinado só para “destravar”.
6. **Retenção/artefatos:** identificar run ID e conclusão, baixar dados necessários dentro da retenção; sumário/`exit_code` não substituem evidência funcional, e artifact sem mascaramento pode conter dados privados.
7. **Revisão regular:** manter a matriz de workflows por categoria, verificar se os testes focados ainda cobrem a mudança e não inferir cobertura universal pelos 556 aprovados.

**Próxima etapa documental:** Etapa 10 — entradas, configuração, instalação e distribuição, em outra PR.
