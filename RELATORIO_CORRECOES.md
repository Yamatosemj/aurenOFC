# Correções da auditoria Auren

17/10/2026 — branch `correcoes-auditoria`, criada a partir de `a7a6fd3e647de2f62b6a51fe570dfe78c4dbe3e8`.

As fases foram executadas na ordem pedida. Cada fase só avançou após os testes permitidos passarem. Há um commit por fase. Não houve merge, push, instalação de dependências ou alteração da main. As PRs #141, #142 e #137 ficaram fora.

Os achados tratados continuavam presentes na releitura (**MANTIDO**). Não houve item pulado como “JÁ CORRIGIDO” ou “INVALIDADO” por suposição. AUD-023, antes suspeita, teve seu mecanismo confirmado com arquivos fictícios. AUD-022 continua suspeita, sem ataque demonstrado. Os relatórios originais foram copiados sem alteração para `docs/auditoria/`, pois essa pasta não existia no checkout.

## O que foi corrigido, fase por fase

### P0 — AUD-001

A autorização agora fica ligada ao caminho e à identidade do arquivo identificado antes da pergunta. Se o destino mudar ou o arquivo for substituído, a leitura é recusada. Cada abertura confere o arquivo efetivamente aberto antes de ler bytes, incluindo as aberturas auxiliares da inspeção. O arquivo certo continua funcionando; negativa e pastas sensíveis continuam impedindo a leitura.

Seis reproduções falharam antes da correção; quatro controles já passavam. Os dez casos passam após corrigir.

A suíte inicialmente parou em um teste PowerShell: o Windows bloqueava o carregamento de um `.ps1`. A mesma falha foi confirmada no código anterior. Após o pedido para corrigir, ajustei a preparação do teste para incluir a função original no comando de teste já executado. A função de proteção e a política do Windows não foram alteradas. Acrescentei recusas por usuário incorreto, falta de aprovação, execução elevada e parada de emergência. Os nove testes dessa área passaram e a suíte deixou de apresentar a falha.

### P1a — AUD-002, 003, 004, 025, 028 e LIV-003

Recusas de foco e fechamento de janela e erro ao abrir atalho agora são falhas explícitas. A recusa de salvar ou esquecer uma lembrança também continua sendo falha ao chegar ao executor comum.

Uma falha pendente é identificada pelos argumentos originais, de forma privada e separada do texto mascarado. Outro valor não apaga a falha, e mudar apenas a ordem dos campos não cria uma operação diferente. A conferência de preenchimento usa o valor original apenas em memória, compara o valor inteiro e respeita a ocorrência selecionada. Os argumentos dos registros continuam mascarados.

O contexto do navegador respeita falhas das leituras que o compõem e preserva informações parciais úteis. As funções antigas ainda usam o adaptador de compatibilidade; não foi migrado todo o navegador.

Onze reproduções falharam antes da correção e um controle já passava. Os doze casos novos passam na suíte final. Dois testes antigos foram atualizados para verificar a identidade privada, mantendo a exigência de não apagar uma falha por causa de outra ação.

### P1b — AUD-005, 006, 007, 009, 012, 026, 030 e LIV-004

Uma verificação de abas esgotada agora termina com falha. A comparação de destinos usa servidor e caminho: um endereço parecido não é aceito como o solicitado. Desligar libera o estado visual de ocupado, mantendo a rejeição de eventos antigos.

A última rodada de ferramentas não solicita outra resposta que ficaria sem processamento. Uma consulta isolada do navegador não cria uma obrigação artificial de verificação, e uma observação sem prova não reinicia o contador dessa verificação.

Resultados grandes de arquivos continuam sendo JSON válido e trazem a continuação calculada a partir do texto realmente entregue. Outros resultados estruturados grandes informam a omissão, sem produzir JSON quebrado.

Na atualização de um controle de tela, o programa conserva a ocorrência e confere identidade e proteção. Se o controle desaparecer ou mudar, a escrita para. O teste usou o trecho real de atualização com controles PowerShell fictícios, sem aplicativo ou dispositivo real.

As oito reproduções falharam antes das correções. A seleção focada terminou com 77 aprovados.

### P2a — AUD-010, 011, 014, 015 e 023

Uma gravação automática recusada gera diagnóstico sem repetir o conteúdo privado. Um trabalho de estratégia recusado não termina como gravação bem-sucedida. Sem identidade de chat, a montagem do contexto não recupera conversas ou estratégias de outros chats.

Sobrescrever o clipboard após ler conteúdo externo exige confirmação. O orçamento geral não foi afrouxado. O contexto existente acompanha as rodadas seguintes, dentro dos mesmos limites de tamanho; estratégias anteriores mostram se falharam e qual foi seu resultado.

A busca de cópias reaplica a política ao destino de cada candidato e confere sua identidade antes de calcular a assinatura. Destinos protegidos ou que exigiriam confirmação são omitidos, sem aprovação automática dentro da varredura. A omissão é sinalizada como limitação.

As sete reproduções falharam antes das correções. Uma expectativa antiga de teste foi atualizada para exigir o contexto na continuação.

### P2b — AUD-034 e 035

Duas verificações que estavam dentro de comentários agora executam de verdade. O teste de raízes recupera a função original, em vez da função fictícia que ele próprio tinha instalado, e verifica também a recusa de um arquivo fora das raízes permitidas.

Os quatro trechos de processos do testador manual entendem o resultado estruturado e exigem os códigos corretos de proteção. Não dependem mais de métodos de texto nesse resultado. Os trechos reais foram testados isoladamente com executores fictícios; a bateria Live não foi iniciada.

As três reproduções falharam antes das correções. A seleção focada terminou com 45 aprovados e um ignorado.

### P3 — AUD-016, 018, 020, 021, 029, 031 e 032

A identificação de CSV lê somente uma amostra de 16.384 caracteres. O cache não reutiliza respostas quando há continuação de outra resposta ou esforço diferente do padrão.

A revisão de intenção transmite seus contadores ao registro da tarefa; o agregador também os reconhece. O contador global é apresentado como do processo, não como de um chat. **AUD-020 foi tratado parcialmente:** os coeficientes de custo existentes continuam estimativas genéricas. Não escolhi preços novos nem consultei faturamento. Chamadas que falham antes de produzir decisão válida continuam sem uso individualizado no registro da tarefa; não é possível inventar tokens que o serviço não informou.

A documentação deixa de apresentar comportamentos antigos de recuperação, override e Standby do Chrome como se ainda fossem os atuais. A busca por nome não apresenta arquivos sem correspondência como resultado. Os dois temporários de UIA são removidos também em falha de início e timeout. O agregador lê o estado de TASK_END pelo nome do campo, sem misturar o evento seguinte.

As nove reproduções falharam antes das correções. A seleção focada terminou com 54 aprovados.

### Fase Live — LIV-001, 002, 005 e 007

Um caminho explícito de `.exe` é validado e usado antes da busca aproximada por nome. Um caminho ausente não abre outro aplicativo. A resposta informa que a abertura foi solicitada e fornece o processo iniciado; não afirma que a janela está pronta. Caminhos explícitos que não identificam um `.exe` válido falham, sem troca silenciosa por outro programa.

Uma observação intermediária não encerra automaticamente pedidos de ação iniciados por local, restrição ou verbo desconhecido. Sequências de operações de janela não terminam localmente só porque a primeira mutação funcionou. O ciclo normal continua responsável por prosseguir ou informar a falha; não foi criado um novo planejador.

Uma pergunta pendente deixa de depender da primeira palavra do pedido. Respostas curtas retomam o pedido e suas restrições no mesmo contexto. Isso não concede autorização local para executar ferramentas.

As oito reproduções falharam antes das correções; a seleção focada terminou com 68 aprovados. A primeira execução ampla revelou uma simulação antiga que fornecia apenas a chamada de ferramenta e dependia do encerramento automático. A simulação passou a fornecer também a resposta final, mantendo as verificações de aprovação e execução. LIV-003 e LIV-004 já haviam sido tratados nas fases anteriores. **LIV-006 foi pulado por decisão de produto; o veto continua impedindo a ação.**

## O que foi pulado e por quê

Todos os itens abaixo foram relidos e permanecem presentes; não são declarados corrigidos.

| Item | Motivo |
| --- | --- |
| AUD-008 | Corrigido na continuação autorizada; veja a atualização abaixo |
| AUD-013 | Corrigido na continuação autorizada: alternativa diferente passa pela política normal |
| AUD-017 | Corrigido na continuação autorizada |
| AUD-019 | Prazos de retenção e alcance da exclusão exigem decisão do proprietário |
| AUD-022 | Corrigido na continuação autorizada: contexto recuperado exige confirmação para efeitos externos |
| AUD-024 | Corrigido na continuação autorizada, com limites físicos descritos abaixo |
| AUD-027 | Corrigido na continuação autorizada; veja a atualização abaixo |
| AUD-033 | Corrigido no instalador, sem instalar nem aprovar o runner real |
| LIV-006 | Corrigido no ciclo do modelo: uma alternativa diferente, revisada e limitada |

AUD-036 pertence exclusivamente à PR #137 e ficou fora por instrução expressa. AUD-020 tem a parte de contagem corrigida e as limitações de custo e falhas anteriores à decisão descritas acima.

## Perguntas para decisão

1. Após duas falhas iguais, deve parar toda a tarefa ou permitir uma alternativa diferente, mantendo os outros limites? (AUD-013)
2. Por quanto tempo guardar conversas, lembranças, registros e capturas? Ao pedir para esquecer, quais classes devem ser apagadas? (AUD-019)
3. Quais tipos de memória devem carregar origem externa e exigir confirmação em tarefas futuras? Como tratar registros antigos sem essa origem? (AUD-022)
4. Qual aprovação explícita deve autorizar a modalidade de testes sem consulta online? (AUD-033)
5. Depois de um veto, o Auren deve apenas explicá-lo ou pode elaborar outra proposta? Se puder, qual o limite? (LIV-006)
6. Resolvido: o proprietário autorizou continuar os itens antes excluídos. Os testes simulados de voz passaram a fazer parte da validação; isso não comprova funcionamento físico.

## Resultado real das suítes amplas

Cada linha é uma execução; os totais se sobrepõem e não devem ser somados como testes diferentes.

| Fase validada | Aprovados | Falhas | Ignorados | Casos de voz excluídos na seleção |
| --- | ---: | ---: | ---: | ---: |
| P0, após corrigir a preparação PowerShell | 781 | 0 | 8 | 2 |
| P1a | 793 | 0 | 8 | 2 |
| P1b | 801 | 0 | 8 | 2 |
| P2a | 808 | 0 | 8 | 2 |
| P2b | 810 | 0 | 8 | 2 |
| P3 | 819 | 0 | 8 | 2 |
| Live, execução final | 827 | 0 | 8 | 2 |

Os oito ignorados dependem de criar links simbólicos, não permitido neste Windows. Não foram transformados em aprovação. Os arquivos `test_voice.py`, `test_voice_v3.py`, `test_voice_installer_cache.py` e `test_confirmation.py` ficaram fora da coleta; o último importa componentes de voz. A seleção `not voice` excluiu dois casos adicionais em arquivos mistos.

Uma execução intermediária de P1a incluiu esses dois casos simulados de voz por erro de seleção; nenhum dispositivo foi acessado. O executor foi corrigido e todas as execuções amplas finais por fase os excluíram.

As reproduções anteriores às correções falharam conforme descrito em cada fase. Também houve falhas intermediárias de preparação e expectativas antigas, corrigidas antes de avançar. Na fase Live, a primeira execução ampla terminou com 826 aprovados e uma falha da simulação descrita acima; o resultado final está na tabela.

A execução final terminou em 44,19 segundos. Isso é duração do teste automatizado, não medição de velocidade do Auren em tarefas reais. Os arquivos novos de regressão ficam em `tests/test_audit_*.py`.

## Ambiente e evidências

Windows, Python 3.13.15. Os testes rodaram em cópias temporárias contendo fontes versionadas e os novos testes, com perfil, OneDrive e temporários fictícios. Não foram copiados `.env`, credenciais, bancos, logs ou `desktop/` reais. Os bancos de teste contêm somente dados fictícios. Nenhuma confirmação real foi aprovada automaticamente.

As saídas de texto e XML de cada execução foram preservadas em `C:\Windows\Temp\auren-correcoes-c704711e41bd461887318de7ea40b7b6`, em pastas identificadas pela fase e por `red`, `green` ou `full`. O executor isolado está em `C:\Windows\Temp\run_auren_audit_tests.py`. São evidências desta manutenção, não logs reais do Auren. A suíte final usa a pasta `live-full-final`.

A main remota consultada foi `70b040d6191237e2f0a291a14b8ea8fb4b78a09d`, com checks anteriores aprovados. Não houve push, disparo de workflow nem validação CI deste branch. Os testes locais não são apresentados como CI remoto.

## O que não foi testado

- Auren com modelo real, API paga, navegador real, foco de janelas, escrita em controles reais, clipboard real ou screenshots.
- Voz, microfone, reprodução de som e dispositivos reais; os itens de voz pendentes também não receberam correção.
- Links simbólicos nos oito casos ignorados, junctions e trocas hostis em todos os sistemas de arquivos do Windows.
- Conteúdo e estado de dados pessoais, bancos, logs, perfis e `.env` reais.
- Uso autônomo após veto, política nova de retenção, migração de origem das memórias ou aprovação de runner.
- PRs #141, #142 e #137; Electron e lembretes não foram incorporados.
- Preços atuais, fatura, saldo ou resistência universal a instruções maliciosas.

Conferir a identidade do arquivo aberto não impede outro processo de alterar os bytes do mesmo arquivo durante a leitura. Os limites de contexto por caracteres permanecem e podem cortar informações em tarefas longas. As correções de conclusão local reduzem os casos reproduzidos; não demonstram compreensão perfeita de qualquer frase nem conclusão física de toda tarefa. A abertura solicitada de um executável não comprova janela pronta.

A pasta não rastreada `desktop/`, preexistente, foi preservada. Nenhuma política do Windows ou do runner foi alterada, nem dados reais foram limpos.

## Continuação autorizada — AUD-027

O proprietário autorizou continuar os itens antes excluídos. Esta atualização prevalece sobre as exclusões de voz descritas no histórico acima. A continuação permanece no branch separado e usa somente cópias temporárias e dados fictícios.

AUD-027: MANTIDO na releitura e corrigido. A fala só simplifica o resultado de uma ferramenta quando a tarefa terminou e a última etapa tem sucesso confirmado. Falhas, cancelamentos e etapas sem confirmação preservam a resposta final, sem anunciar uma ação bem-sucedida por causa do nome da ferramenta.

Antes da correção: cinco reproduções falharam e um controle passou. Depois: 17 testes focados passaram. A suíte ampla desta etapa passou com 920 aprovados, zero falhas e oito ignorados (46,96 segundos), incluindo testes simulados de voz e confirmação. A preparação de cinco snapshots antigos foi completada com os campos reais de estado e sucesso. Houve duas falhas intermediárias por esses dados ausentes; outra execução incluiu os dois testes ainda vermelhos de AUD-008. A validação de AUD-027 excluiu somente esse arquivo de reprodução da próxima etapa, ainda sem correção. Evidência: `voice-status-validated/result.xml` na pasta temporária já indicada.

Não houve microfone, som, download de modelos, API paga ou interação física. Os demais itens pendentes continuam em andamento.

## Continuação autorizada — AUD-008

MANTIDO na releitura e corrigido. O limite de áudio passou a valer dentro do recebimento dos blocos, incluindo o trecho anterior ao pressionamento da tecla. Ao atingir o tempo máximo, a gravação também para antes de esperar a tecla ser solta. Manter a tecla pressionada não faz o buffer crescer sem limite.

As duas reproduções falharam antes: receberam 3.000 e 180 amostras para um limite de 100. Depois passaram, junto com os testes de voz existentes: 42 aprovados. A suíte completa passou com 922 aprovados, zero falhas e oito ignorados, em 44,72 segundos (`voice-buffer-full/result.xml`). Os oito ignorados continuam relacionados a links simbólicos no Windows. Nenhum dispositivo foi usado.

## Continuação autorizada — AUD-017 e AUD-024

Ambos MANTIDOS na releitura e corrigidos. O reconhecimento de voz separa os arquivos por origem e revisão e verifica a identificação do cache. Os arquivos antigos são preservados; pode ser necessário baixar o modelo novamente no primeiro uso. A revisão padrão ainda é `main`; para fixar uma versão, configure `AUREN_ASR_REVISION` com um commit remoto. Não houve download nesta manutenção.

O modo de voz agora limita as filas, avisa quando descarta áudio excedente, sinaliza a parada da captura e encerra a sessão e os recursos do Harness. A espera pelo TTS cancelado tem prazo de um segundo; se ele não responder, o canal encerra. A gravação de memória que ultrapassar o prazo é informada. Não se promete interromper à força um driver ou uma escrita que já começou.

As duas reproduções de AUD-017 e as três iniciais de AUD-024 falharam antes da correção. Após as correções e controles adicionais, 54 testes focados passaram. A suíte completa terminou com 931 aprovados, zero falhas e oito ignorados em 46,26 segundos (`voice-p2a-full/result.xml`). Foram simulados cache completo de origem diferente, manifesto incompatível, saída do canal, fila cheia, TTS sem resposta e gravação de memória bloqueada. Nenhum hardware foi acessado.

## Continuação autorizada — AUD-013

MANTIDO na releitura e corrigido. A trava de duas falhas iguais bloqueia repetir aquela mesma ação. Uma alternativa diferente continua sujeita às permissões e confirmações normais. Permanecem os limites de três falhas consecutivas e de ações por tarefa. Nenhuma confirmação é aprovada automaticamente.

A decisão anterior foi resolvida dentro da autorização para continuar: permitir considerar uma alternativa, mantendo as outras travas. Duas reproduções falharam antes e um controle passou. Depois: 11 testes focados aprovados e suíte completa com 934 aprovados, zero falhas e oito ignorados (44,94 segundos; `alternative-guard-full/result.xml`).

## Continuação autorizada — AUD-022

MANTIDO como lacuna de propagação e corrigido de forma conservadora. As seções recuperadas carregam uma identificação separada do texto. O Harness informa essa origem ao mesmo gerenciador de permissões usado para executar ferramentas. Isso vale também para registros antigos: conteúdo lembrado não recebe a autoridade do pedido atual. Consultas continuam possíveis; ações com efeitos externos passam a exigir confirmação quando houver contexto recuperado. Isso pode aumentar os pedidos de confirmação em conversas longas.

A reprodução com duas tarefas fictícias mostrou que a segunda perdia a exigência de confirmação. Falhou antes e passou depois; não se demonstrou um ataque contra um modelo real. Foram 40 testes focados aprovados e suíte completa com 935 aprovados, zero falhas e oito ignorados (47,78 segundos; `memory-origin-full/result.xml`). Não houve migração nem leitura de bancos reais.

## Continuação autorizada — AUD-033

MANTIDO na releitura e corrigido no instalador. Uma instalação nova exige a opção explícita `-AutorizarValidacaoOffline` e grava a aprovação correspondente à política copiada. Uma instalação antiga incompleta não é mais anunciada como concluída. O controle manual e os backups são preservados. O instalador não foi executado no perfil real e nenhuma autorização real foi concedida.

Três reproduções válidas falharam antes. Uma tentativa anterior foi impedida pela política de execução do Windows; a preparação foi ajustada para executar apenas o texto revisado na pasta fictícia, sem mudar essa política. Depois, 12 testes focados passaram; suíte completa: 938 aprovados, zero falhas e oito ignorados (48,67 segundos; `chat-installer-full/result.xml`).

## Continuação autorizada — LIV-006

MANTIDO na releitura e corrigido no ciclo normal do modelo. Depois de um veto semântico, o Auren pode propor uma única alternativa diferente, se ainda houver rodadas disponíveis. A ação vetada não é executada e não pode reaparecer com argumentos equivalentes. A alternativa passa novamente pelo revisor e pelo caminho normal de permissões. Outro veto, repetição ou ausência de alternativa encerra sem declarar sucesso. Não se reinicia o orçamento de ações.

Decisão adotada dentro da autorização para continuar: um replanejamento, nunca aprovação automática. Atalhos locais vetados continuam encerrando imediatamente; esta mudança trata o ciclo do modelo usado no achado Live. Quatro reproduções falharam antes e um controle passou. Depois foram 63 testes focados aprovados e suíte completa com 943 aprovados, zero falhas e oito ignorados (48,65 segundos; `veto-replan-full/result.xml`). Modelo e ferramentas eram fictícios.
