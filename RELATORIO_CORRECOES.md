# Correções da auditoria Auren

Data: 17/10/2026. Branch: `correcoes-auditoria`.

**P0 passou na suíte ampla após a correção do teste PowerShell.** As fases seguintes serão executadas na ordem autorizada. Este documento distingue resultados anteriores e atuais; não declara as fases ainda pendentes como concluídas.

## O que foi corrigido

### P3 — AUD-016, 018, 020, 021, 029, 031 e 032

Todos estavam **MANTIDOS**. As nove reproduções falharam antes das correções. A identificação de CSV lê somente a amostra de 16.384 caracteres. O cache não reutiliza uma resposta quando há continuação de outra resposta ou esforço diferente do padrão. A revisão de intenção transmite seus contadores de uso ao registro da tarefa, e o agregador também os reconhece. O contador global é apresentado como do processo, não de um chat.

A documentação deixa de apresentar o override, a recuperação de falhas e o Standby do Chrome como se ainda tivessem os comportamentos antigos. A busca por nome não apresenta arquivos com pontuação zero como correspondência. Os dois temporários de UIA são removidos também em erro de início e timeout. O agregador lê o campo de estado de TASK_END sem misturar o evento seguinte.

**Limite de AUD-020:** os coeficientes de custo existentes continuam estimativas genéricas; não foram escolhidos preços novos nem consultado faturamento. Sem retorno de uso do serviço, tokens desconhecidos não podem ser inventados. As chamadas que falham antes de produzir decisão válida continuam sem uso individualizado no registro da tarefa.

Seleção focada: **54 aprovados**. Suíte ampla: **819 aprovados, zero falhas, oito ignorados, dois casos de voz excluídos**, em 45,02 segundos.

### P2b — AUD-034 e AUD-035

Ambos estavam **MANTIDOS**. Três reproduções falharam antes de corrigir. Duas verificações que estavam dentro de comentários agora executam de verdade. O teste de raízes restaura a função original capturada antes da substituição e verifica também a recusa de um arquivo fora das raízes permitidas. O testador manual de processos usa o resultado estruturado e exige os códigos corretos de proteção, em vez de chamar métodos de texto nesse resultado.

Os quatro blocos reais do testador foram executados isoladamente com executores fictícios; a bateria Live não foi iniciada. **AUD-033:** MANTIDO por releitura, sem alteração porque aprovar o modo sem consulta online exige decisão explícita de autorização. Não gravei aprovações novas nem alterei a política instalada.

Seleção focada: **45 aprovados e um ignorado**. Suíte ampla: **810 aprovados, zero falhas, oito ignorados, dois casos de voz excluídos**, em 44,86 segundos.

### P2a — AUD-010, 011, 014, 015 e 023

Sete reproduções falharam antes de corrigir. AUD-010, 011, 014 e 015 estavam **MANTIDOS**; AUD-023, antes suspeita, foi confirmado em uma busca fictícia que tentava calcular a assinatura de um destino protegido.

Recusas de gravação automática agora geram aviso técnico sem repetir o conteúdo privado; uma estratégia recusada não termina como trabalho de memória bem-sucedido. Sem identidade de chat, a montagem de contexto não busca conversas e estratégias de outros chats. Sobrescrever o clipboard após leitura externa exige confirmação, sem mudar o orçamento geral. O contexto existente acompanha as rodadas seguintes, com os mesmos limites de tamanho, e estratégias anteriores mostram se falharam e qual foi seu resultado. A busca de cópias reaplica a política a cada destino efetivo, não pede confirmações dentro da varredura e confere a identidade antes de calcular assinaturas.

**AUD-017 e AUD-024:** MANTIDOS por leitura, sem correção por serem voz. **AUD-019:** MANTIDO, exige política de retenção e exclusão. **AUD-022:** MANTIDO como suspeita: o esquema não transporta origem estruturada entre tarefas; não foi demonstrado ataque. Definir quais memórias devem exigir confirmação por origem é decisão de produto e ficou pendente; não rotulei toda lembrança como ataque nem removi a proteção atual.

Uma expectativa antiga de teste foi atualizada para exigir o contexto na continuação. Suíte ampla: **808 aprovados, zero falhas, oito ignorados e dois casos de voz excluídos**, em 43,79 segundos. A preservação do contexto continua limitada pelo orçamento de caracteres existente; não foi criado um sistema novo de memória ou de extração de restrições.

### P1b — AUD-005, 006, 007, 009, 012, 026, 030 e LIV-004

Todos estavam **MANTIDOS**; oito reproduções falharam antes de corrigir. A verificação esgotada de abas agora encerra com falha; endereços são comparados por servidor e caminho, não por prefixo. Desligar libera o estado visual de ocupado sem aceitar eventos antigos. A última rodada de ferramentas não pede outra resposta que ficaria sem processamento. Uma leitura isolada do navegador não cria uma falsa obrigação de verificação e uma observação sem prova não reinicia seu contador.

O corte de resultados de arquivos preserva JSON válido e calcula a continuação a partir do texto realmente entregue. Para outros resultados estruturados grandes, informa a omissão sem produzir JSON quebrado. A atualização de um controle de tela conserva a ocorrência e confere sua identidade e proteção; se o controle mudar ou desaparecer, a escrita para. O teste executou o trecho real de atualização com controles PowerShell fictícios, sem aplicativo ou dispositivo real.

**AUD-008:** MANTIDO por leitura, pulado por ser voz. **AUD-013:** MANTIDO, pulado por depender da decisão sobre parar toda a tarefa ou permitir alternativas após falhas repetidas. A regra existente foi preservada.

Testes focados: **77 aprovados**. Suíte ampla: **801 aprovados, zero falhas, oito ignorados, dois casos de voz excluídos**, em 45,22 segundos. Não houve teste visual real nem medição de custo/latência de API.

### P1a — AUD-002, AUD-003, AUD-004, AUD-025, AUD-028 e LIV-003

Todos esses achados estavam **MANTIDOS** na releitura. Os novos testes reproduziram onze falhas antes das alterações (um controle já passava).

- Recusas de foco e fechamento de janela, e erro ao abrir atalho, agora são falhas explícitas. Não foi alterada a capacidade do Windows de negar foco ou fechamento.
- A recuperação de uma falha compara uma assinatura privada dos argumentos originais. Valores diferentes não se confundem por causa do mascaramento; mudar apenas a ordem dos campos JSON não cria outra operação. Os registros continuam mascarados.
- A conferência de um campo preenchido usa o valor original apenas em memória durante a tarefa. Ela compara o valor inteiro e a ocorrência selecionada, sem aceitar um prefixo como resultado correto.
- O contexto do navegador passa a respeitar falhas das leituras que o compõem e conserva informações parciais úteis. Componentes antigos ainda passam pelo adaptador legado; não foi migrado todo o navegador para um contrato novo.
- A recusa de salvar ou esquecer uma lembrança permanece falha ao chegar ao executor comum.

**AUD-027:** MANTIDO por releitura, mas pulado porque exige testes do formatador de voz, excluídos pela regra 10. Nenhuma correção sem reprodução foi aplicada.

Os doze novos testes passaram. A seleção inicial detectou dois testes antigos que esperavam argumentos em claro na identidade das pendências; foram atualizados para conferir a mesma identidade em hash, conservando a exigência de que outra ação não apague a falha. Suíte ampla final: **793 aprovados, zero falhas, oito ignorados e dois casos de voz excluídos**, em 42,70 segundos. Uma execução intermediária incluiu dois testes simulados de voz de arquivos mistos por erro na seleção; nenhum dispositivo foi acessado. O executor de testes foi corrigido e a execução final excluiu esses casos.

### P0 — AUD-001

Situação na releitura: **MANTIDO**. A versão inicial ainda podia pedir autorização para um arquivo e, depois da resposta, ler outro. Reproduzi a falha com arquivos fictícios antes de alterar o programa: seis testes falharam e quatro controles passaram.

Agora a autorização fica ligada ao caminho e à identidade do arquivo identificado antes da pergunta. O programa cancela a leitura se o destino mudar. Também confere o arquivo efetivamente aberto antes de ler qualquer conteúdo, para detectar substituição no mesmo caminho ou troca no instante de abrir. Essa conferência acompanha as aberturas usadas para conteúdo, identificação de formato, cálculo da assinatura e informações de origem.

A leitura de pastas sensíveis continua bloqueada. A negativa do usuário continua impedindo a leitura. Nada responde às confirmações reais pelo usuário. Os testes usam respostas programadas somente em objetos fictícios de teste.

Há dez novos testes em `tests/test_audit_p0.py`: troca de destino durante a pergunta, substituição no mesmo endereço, troca ao abrir, leitura do arquivo correto e negativa; cada situação cobre leitura e inspeção. Os documentos sobre permissões e arquivos foram atualizados. Os dois relatórios fornecidos foram copiados sem alteração para `docs/auditoria/`, pois essa pasta não existia no checkout.

## Bloqueio inicial e correção do teste

O teste `tests/test_chat_policy_setup.py::test_local_guard_requires_owner_and_correct_comment_format` tenta carregar um arquivo PowerShell. O Windows recusa esse carregamento porque a execução de scripts está desabilitada. O teste termina antes de verificar a regra que pretendia testar.

Reproduzi a mesma falha em uma cópia com os três arquivos de código originais, recuperados do Git, sem a correção de P0. Portanto, essa falha não foi introduzida pela correção. Mesmo assim, a regra 5 exige a suíte passando antes da próxima fase. A regra 7 impede reduzir proteções para obter esse resultado. Não alterei política do Windows, proteção do runner, teste bloqueado ou autorização. Não marquei a falha como aprovada nem retirei esse teste da suíte.

Foram feitas duas execuções amplas. A segunda confirma o estado final do código. Não avancei para outra fase.

Após o pedido de corrigir o bloqueio, reproduzi novamente a falha antes de editar. O teste agora inclui a função versionada no comando de teste que já executava, em vez de carregar um arquivo `.ps1`. Não altera a política de execução do Windows nem a proteção do Auren. A função de produção não foi editada. Ampliei os casos negativos: comando inválido, autor e ator incorretos, falta de aprovação, execução elevada e parada de emergência; cada recusa precisa apresentar o motivo esperado. Os nove testes da área passaram. Em seguida, a suíte ampla passou: **781 aprovados, zero falhas, oito ignorados e dois casos de voz excluídos**, em 43,02 segundos. O bloqueio está resolvido e P0 está validada dentro do escopo automatizado permitido.

## Resultado real dos testes

| Execução | Aprovados | Falhas | Ignorados | Excluídos na seleção |
| --- | ---: | ---: | ---: | ---: |
| Reprodução válida de AUD-001, antes da correção | 4 | 6 | 0 | 0 |
| P0 e testes de arquivos, após a correção | 49 | 0 | 1 | 0 |
| Seleção final de P0, arquivos, permissões, contratos e origem externa | 81 | 0 | 1 | 0 |
| Suíte ampla, primeira execução | 775 | 1 | 8 | 2 |
| Teste bloqueado, usando o código original | 0 | 1 | 0 | 0 |
| Suíte ampla, segunda execução | 775 | 1 | 8 | 2 |
| Testes do PowerShell após a correção de preparação | 9 | 0 | 0 | 0 |
| Suíte ampla após resolver o bloqueio | 781 | 0 | 8 | 2 |

As execuções se sobrepõem: os totais não devem ser somados como testes diferentes. Os oito casos ignorados dependem da criação de links simbólicos, que o Windows não permitiu. Os dois casos excluídos na seleção ampla são de voz em arquivos mistos. Arquivos inteiros de testes de voz também foram deixados fora, conforme a regra 10; não estão incluídos nessas contagens.

As execuções amplas levaram 41,47 e 39,28 segundos. A seleção final levou 1,55 segundo. Os arquivos inteiros excluídos foram `test_voice.py`, `test_voice_v3.py`, `test_voice_installer_cache.py` e `test_confirmation.py` (este importa componentes de voz na coleta). Os demais arquivos de teste foram coletados, com a seleção `not voice` para os casos de voz em arquivos mistos.

Comandos e resultados detalhados ficaram em uma pasta criada para este trabalho: `C:\Windows\Temp\auren-correcoes-c704711e41bd461887318de7ea40b7b6`. Há saídas de texto e resultados XML em `p0-full-1`, `p0-full-2`, `p0-baseline` e `p0-final`. O executor que prepara cópias isoladas está em `C:\Windows\Temp\run_auren_audit_tests.py`. Esses arquivos de teste foram preservados; não são logs reais do Auren.

Na preparação inicial, a pasta temporária padrão ficava dentro de AppData e foi corretamente bloqueada. Também ajustei a comparação de texto do pedido para o formato de caminhos do Windows. Esses resultados de preparação não foram usados para confirmar o defeito. A reprodução válida, com arquivos em pasta temporária própria fora de AppData, foi executada antes da correção e é a primeira linha da tabela.

Ambiente: Windows, Python 3.13.15. A suíte ampla e a seleção final rodaram em cópias temporárias contendo apenas fontes versionadas e o novo teste. O perfil do usuário, OneDrive e temporários desses processos apontavam para pastas fictícias. Não foram copiados bancos, logs, `.env`, credenciais ou a pasta `desktop/` preexistente. Nenhuma chamada ao modelo foi necessária.

## O que ficou pendente, fase por fase

Os itens abaixo **não foram revalidados nem corrigidos nesta execução**, pois a barreira de P0 impediu sua fase. Não receberam rótulo de “já corrigido” ou “invalidado” por suposição.

| Fase | Itens pendentes | Motivo |
| --- | --- | --- |
| P1a | AUD-002, 003, 004, 025, 027, 028; LIV-003 | P0 sem aprovação da suíte ampla |
| P1b | AUD-005, 006, 007, 008, 009, 012, 013, 026, 030; LIV-004 | Dependência de P1a |
| P2a | AUD-010, 011, 014, 015, 017, 019, 022, 023, 024 | Dependência das fases anteriores |
| P2b | AUD-033, 034, 035 | Dependência das fases anteriores |
| P3 | AUD-016, 018, 020, 021, 029, 031, 032 | Dependência das fases anteriores |
| Live | LIV-001, 002, 005, 006, 007 | Dependência das fases anteriores; nenhum ensaio real iniciado |

AUD-036 pertence exclusivamente à PR #137 e ficou fora do trabalho, conforme pedido. As PRs #141, #142 e #137 não foram incorporadas.

## Decisões para o proprietário

Estas perguntas vêm das recomendações dos relatórios; não foram decididas nem implementadas:

1. **AUD-013:** depois de duas falhas iguais, o Auren deve parar toda a tarefa ou permitir uma alternativa diferente, mantendo os outros limites?
2. **AUD-019:** por quanto tempo guardar conversas, lembranças, registros e capturas? O que deve ser apagado quando o usuário pedir para esquecer?
3. **LIV-006:** depois de uma proposta vetada, o Auren deve apenas explicar o veto ou pode elaborar outra proposta dentro de um limite explícito? Qual deve ser esse limite?
4. **AUD-033:** qual aprovação explícita deve autorizar a modalidade de testes sem consulta online? Não adicionei aprovação silenciosa ao instalador.
5. **AUD-008, 017, 024 e 027:** como tratar as correções que dependem de testes simulados de voz, já que esta tarefa exclui testes de voz? Nenhum desses testes foi executado aqui.

A falha de preparação do teste PowerShell foi resolvida sem alterar a configuração do Windows.

## O que não foi testado

- Uso real do Auren, API paga, navegador real, foco de janelas, UI Automation, clipboard ou capturas de tela.
- Voz, microfone, modelos de áudio, reprodução de som e outros dispositivos.
- Links simbólicos reais nos oito casos ignorados; junctions e substituição hostil de arquivos em todas as configurações de Windows.
- Conteúdo ou estado dos bancos, logs, perfis e `.env` reais.
- Funcionamento das correções das fases seguintes, pois elas não foram iniciadas.
- CI deste branch: houve apenas consulta aos resultados já existentes da main; não foi feito push nem disparo de workflow.

A comparação da identidade antes de ler protege o alvo aberto; não promete impedir que outro processo altere os bytes do mesmo arquivo durante a leitura. Não é uma auditoria universal de segurança do sistema de arquivos.

## Estado de entrega

Base local: `a7a6fd3e647de2f62b6a51fe570dfe78c4dbe3e8`, na branch anterior `teste-pr-149-atualizada`. Main remota consultada: `70b040d6191237e2f0a291a14b8ea8fb4b78a09d`, com três checks aprovados na consulta. Esses checks são anteriores e não aprovam este branch.

Entrega em um único commit de P0, incluindo a correção, o teste, a documentação e este relatório com a falha ampla explícita. Nenhum commit de fase posterior. Nenhum merge, push, instalação ou alteração de dados pessoais. A pasta não rastreada `desktop/`, que já existia, foi preservada.
