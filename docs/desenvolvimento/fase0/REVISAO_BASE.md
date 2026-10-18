# Fase 0 — revisão da base e das PRs #153 e #152

Data: 18/10/2026. **Atualização: reconciliação autorizada e implementada na PR #154; F0-SEG-001 resolvido nos testes.** A revisão das alterações restantes foi concluída em [REVISAO_FINAL.md](REVISAO_FINAL.md), com limites explícitos. O registro da descoberta original foi preservado abaixo.

## Reconciliação após autorização do proprietário

Foi preservada a implementação única da #153 que retorna ToolResult, caminho, PID e inicialização solicitada, sem afirmar que a janela está pronta. Foi incorporada a exigência de confirmação da #152 e sua orientação de preservar o caminho exato no registry. As duas implementações alternativas não foram mescladas nem duplicadas.

A identificação de caminho foi concentrada em `core/utils.py::caminho_explicito_programa`, usada pela permissão e pelo executor, sem consultar disco. Além de absolutos e UNC, caminhos relativos com separador e caminhos relativos a uma unidade exigem confirmação para não contornar a proteção usando outra forma de escrever o mesmo alvo. Aspas simples ou duplas correspondentes são reconhecidas pelos dois componentes. Nomes comuns de aplicativos mantêm a política anterior.

Antes da correção, a seleção ampliada apresentou **10 falhas e cinco aprovações**. Depois, a seleção focada passou com **89 aprovados**. Suíte completa: **974 aprovados, zero falhas, oito ignorados**, em **49,79 segundos**. Nenhum teste foi marcado como falha esperada ou teve sua exigência reduzida. A seleção inclui recusa, confirmação positiva exclusivamente simulada, caminho exato, aspas, arquivo ausente, diretório, extensão inválida e falha de inicialização. `Popen` e efeitos são simulados; nenhum programa real foi executado e nenhuma confirmação real foi aprovada automaticamente.

Evidência local em [RESULTADOS_RECONCILIACAO.json](RESULTADOS_RECONCILIACAO.json). Não houve API paga, Live ou alteração de main. Essa correção resolveu a divergência examinada; a revisão restante foi posteriormente encerrada no documento final, antes do avanço.

## Registro da revisão inicial — antes da reconciliação

## Referências consultadas

| Referência | HEAD consultado | Situação no GitHub |
| --- | --- | --- |
| main | `70b040d6191237e2f0a291a14b8ea8fb4b78a09d` | Preservada |
| [PR #153](https://github.com/Yamatosemj/aurenOFC/pull/153) | `7df474bb2f6a315ffede684c712999addddb5873` | Aberta, rascunho, base main, três checks aprovados |
| [PR #152](https://github.com/Yamatosemj/aurenOFC/pull/152) | `1720a5e18e48e1325feafc7a06b3718a45031bf4` | Aberta, rascunho, base main, três checks aprovados |

O ancestral comum das duas PRs é a main consultada. A #152 não é ancestral da #153. A #153 reúne as correções da auditoria; a #152 trata especificamente de abertura de executável por caminho absoluto. Não é seguro tratá-las como correções independentes e somáveis sem revisão.

Foram conferidos os metadados atuais, os diffs das duas PRs nos arquivos sobrepostos, a implementação de abertura, a classificação e autorização de programas, o contrato do Dispatcher e os testes relacionados. Os componentes de tarefa, planejamento, fila, trace e interface foram identificados para evitar duplicação nas próximas fases. A revisão integral de todos os arquivos da #153 foi interrompida ao confirmar o bloqueio abaixo.

## Sobreposição e diferenças

| Arquivo/contrato | #152 | #153 | Consequência |
| --- | --- | --- | --- |
| `tools/applications.py` | Prioriza `.exe` absoluto antes de buscar por nome; retorna texto de inicialização solicitada | Também prioriza caminho explícito; retorna ToolResult com PID e distingue pedido de abertura de janela pronta | Implementações alternativas do mesmo comportamento; não manter as duas |
| `core/permission_manager.py` | Usa `ntpath.isabs` e exige confirmação para caminho absoluto, incluindo caminho Windows com aspas | Tem outras correções de permissões da auditoria, mas não essa exigência | A base candidata deixa executar caminho explícito sem essa confirmação |
| `core/tools_registry.py` | Orienta preservar o caminho exato | Não inclui essa atualização da #152 | Descrição precisa acompanhar o contrato reconciliado |
| Testes | Casos de caminho e classificação de permissão | Testa precedência do caminho e ausência de substituição por busca aproximada | Os testes da #153 não verificavam a confirmação específica |
| `AUREN_STATE.md` | Registra a correção específica | Registra o conjunto de correções | Atualizar resumo a partir do resultado final; não substituir um histórico pelo outro |

Uma simulação com `git merge-tree --write-tree --name-only <HEAD153> <HEAD152>` confirmou conflito de conteúdo em `tools/applications.py`. Esse comando calculou uma árvore temporária no banco de objetos Git; não criou commit, não mudou refs, não alterou arquivos de trabalho e não mesclou PRs. A resolução não foi aplicada. O fato de ambas aparecerem individualmente como mescláveis com main não prova que possam ser combinadas entre si.

## Bloqueio F0-SEG-001 — confirmação ausente para executável explícito

No HEAD da #153, `_classificar_programa` só eleva nomes com termos considerados arriscados. Um caminho como `C:\AurenFicticio\Editor.exe` recebe AUTO. O Dispatcher respeita essa classificação e chega ao handler sem perguntar. A #152 acrescenta explicitamente a confirmação de caminhos absolutos.

A reprodução usa o Dispatcher e o PermissionManager verdadeiros e substitui somente o handler de abertura por uma função que conta chamadas. O canal de confirmação sempre nega. Nenhum executável foi criado ou iniciado, nenhum caminho de rede foi acessado e não houve chamada ao modelo. O teste mede o comportamento da proteção, sem depender de uma resposta da IA.

Foram testados caminho Windows normal, caminho com espaços e aspas e caminho UNC fictício. Nos três casos, a #153 apresentou **zero perguntas, uma chamada ao efeito simulado e resultado de sucesso**; o esperado era uma pergunta, zero efeitos e recusa. O controle com nome comum de aplicativo manteve o comportamento automático existente.

| Mesmo teste, em cópias isoladas do Git | Passaram | Falharam | Erros de preparação |
| --- | ---: | ---: | ---: |
| main consultada | 1 | 3 | 0 |
| HEAD da #152 | 4 | 0 | 0 |
| HEAD da #153 | 1 | 3 | 0 |

A falha do teste de política na main não demonstra que seu executor antigo já abria o caminho exato: esse executor ainda tinha o problema de busca aproximada. Demonstra que a regra de confirmação estava ausente. A #153 implementa a abertura exata sem acrescentar a proteção que a #152 propõe para ela.

Evidência por SHA, ambiente e cópia temporária em [RESULTADOS_COMPARACAO.json](RESULTADOS_COMPARACAO.json). O teste está em [test_phase0_executable_confirmation.py](../../../tests/test_phase0_executable_confirmation.py) e deve permanecer falhando até a proteção ser corrigida. Foi incluído na coleta normal da suíte, sem mudar os critérios ou marcar como falha esperada.

Os checks anteriores aprovados da #153 e os 959 testes locais da etapa anterior não cobriam esse contrato. Eles não substituem esta nova reprodução. O teste Live anterior de executável também não comprovava a confirmação específica de caminho absoluto. Essa lacuna limita a conclusão anterior de preservação integral das proteções.

A suíte completa foi repetida nesta fase, incluindo os quatro novos casos: **960 passaram, três falharam e oito foram ignorados**, em **50,48 segundos**, exit code **1**. As três falhas são exatamente as reproduções de confirmação ausente; nenhum outro teste falhou. Os oito ignorados exigem links simbólicos indisponíveis no ambiente. Os testes não foram relaxados para tornar essa base aprovada.

Execução local isolada: `py -3.13 -B C:\Windows\Temp\run_auren_audit_tests.py phase0-full-regression --tb=short`. A cópia e o JUnit estão em `C:\Windows\Temp\auren-correcoes-c704711e41bd461887318de7ea40b7b6\phase0-full-regression`. O script copiou somente fontes versionadas, retirou credenciais e usou perfil temporário. Para reproduzir o achado em outra cópia igualmente isolada: `python -m pytest tests/test_phase0_executable_confirmation.py -q`.

## Base e sequência

Não foi estabelecida uma base aprovada para a Fase 1. A branch de revisão deriva da #153 apenas para registrar o bloqueio e seus testes, sem alterar produto. A PR de revisão usa `correcoes-auditoria` como base para isolar esse diff.

Para desbloquear, é necessário conciliar a abertura estruturada da #153 com a proteção da #152, preservar a confirmação e os demais guards, harmonizar o contrato e os testes, concluir a revisão restante e passar a suíte completa. Não basta escolher uma das branches ou mesclar as duas automaticamente. A correção não foi improvisada porque o proprietário determinou interromper a sequência diante de risco de segurança.

O plano e os critérios de retomada estão em [CICLO_DESENVOLVIMENTO.md](../../../CICLO_DESENVOLVIMENTO.md). As fases 1 a 5 não foram implementadas nem abertas em paralelo.

## Limites desta fase

Sem API paga, Live, programas reais, dados pessoais, leitura de `.env`, bancos ou logs reais, alterações de main, merge ou alteração de workflows. Os testes foram executados com perfis e dados fictícios em cópias temporárias. A reprodução contém apenas falhas da proteção e um controle; não valida todas as capacidades do produto ou a totalidade da #152. Os workflows hospedados existentes disparam PRs com base main; a PR empilhada desta revisão pode não receber esses checks. Ausência de check não equivale a aprovação, e nenhum workflow será alterado para contornar isso.
