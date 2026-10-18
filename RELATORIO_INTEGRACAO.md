# Preparação da integração — PRs #153 a #160

## Conclusão

**Candidata consolidada preparada para teste manual isolado no Windows.** Branch `integracao/prs-153-160-20261018`, criada em worktree separado. Nenhuma alteração ou merge na main; nenhum commit exclusivo das PRs #141/#142 incluído. Nenhuma funcionalidade nova. O CI final Windows/Linux e seu SHA devem ser consultados na PR desta candidata.

Os testes locais terminaram com **1.073 aprovados, zero falhas, oito ignorados e zero avisos**, em **72,54 segundos**, sob supervisor Windows. A execução promoveu avisos de exceção em thread a erro. Os oito ignorados dependem de links simbólicos indisponíveis no ambiente. Os oito controles manuais automatizados da interface também passaram. Isso permite começar a avaliação humana da candidata; não equivale a autorizar merge, produção ou uso de dados pessoais.

## Dependências e consolidação

Main consultada: `70b040d6191237e2f0a291a14b8ea8fb4b78a09d`. Os HEADs foram congelados na preparação e sua ascendência foi verificada com Git, além da consulta ao GitHub. Todas as PRs estavam abertas e mergeáveis em relação à sua própria base; esse status isolado não foi usado como aprovação funcional.

| PR | HEAD conferido | Depende de | Papel |
| --- | --- | --- | --- |
| #153 | 7df474b | main | Correções da auditoria |
| #154 | 60033fd | #153 | Reconcilia #152 e confirmações; supervisor |
| #155 | 3e93696 | #154 | Persistência e correção posterior do supervisor |
| #156 | a2b0961 | #155 | Planejamento, retomada, limites e verificação |
| #157 | 2313f1d | #156 | Rotinas com autorização e escopo |
| #158 | 29dd494 | #157 | Controles na interface existente |
| #159 | a4e1f8b | #158 | Integração e interface isolada |
| #160 | f1ae0e9 | #159 | Confirmação de arquivos e revisão da resposta |

Cada HEAD anterior é ancestral do seguinte e a base de cada PR coincide com o HEAD anterior. A #160 já contém a cadeia toda. A branch temporária começou na main congelada e avançou com `merge --ff-only` por cada HEAD da sequência. Resultado anterior aos testes/documentos desta etapa: árvore idêntica à #160. **Zero conflitos de texto, zero resoluções manuais e zero duplicações por cherry-pick.**

A #152 não foi mesclada separadamente. A #154 mantém seu comportamento relevante com implementação única, resultado estruturado e confirmação independente para caminhos explícitos. Foram conferidos o executor e PermissionManager atuais, além dos 15 testes da reconciliação que continuam na suíte. Reaplicar a #152 duplicaria o assunto e poderia reintroduzir o contrato antigo.

Os conjuntos de commits exclusivos de #141/#142 não têm interseção com a candidata. Os arquivos de Electron e histórico de conversas exclusivos dessas PRs também não estão na árvore. O `desktop/` não versionado e os outros worktrees existentes não foram lidos/copiados nem modificados.

## Sobreposições e riscos entre fases

| Área em comum | O que foi conferido | Evidência principal |
| --- | --- | --- |
| #153/#154/#160, permissões e executáveis | Caminho explícito não passa por busca aproximada; confirmação permanece; raiz permitida não reduz CONFIRM | Testes de reconciliação e de correções Live; negação pelo HTTP/fábrica real |
| #154/#155, supervisor | Versão final mantém espera por descendentes, Job e handles; não reinstala controlador pessoal | Suíte existente de contenção/timeout/limpeza e supervisão desta bateria |
| #155/#156/#158, armazenamento e retomada | Mesmo TaskManager; checkpoint antes dos efeitos; estado, chat, limites e identidade preservados | Novo caso integrado HTTP com encerramento/reabertura; casos existentes entre processos |
| #156/#157/#158, execução e rotinas | Agendamento não cria executor paralelo nem restaura aprovação; UI usa o mesmo Harness; geração e escopo continuam ativos | Nova rotina fictícia pela UI/HTTP, mais testes existentes de revogação/expiração e sessão obsoleta |
| #156/#160, conclusão | Resposta candidata segue para provider/revisor e exige answer_status e referências; falha não vira sucesso | Novo caso pela fábrica real; regressões de resposta errada/campo ausente/referência inválida |
| #158 e fábrica principal | Foram exercitados os callbacks realmente ligados por auren.criar_harness, não apenas um Harness montado pela fixture | Novo teste com worker padrão, Router, provider, Dispatcher e arquivos reais fictícios |

O mapa completo de arquivos em comum e SHAs está em [EVIDENCIAS.json](docs/integracao/EVIDENCIAS.json). Há sobreposição de código sem conflito de Git; por isso a verificação não ficou apenas na ascendência. Não foi feita uma nova auditoria formal de todas as linhas do produto ou prova universal de segurança.

## O que mudou nesta preparação

**Código de produção idêntico ao HEAD da #160.** Foram adicionados quatro cenários integrados e sua fixture isolada, relatório/roteiro, evidências e correção de captura em dois arquivos de testes. Não se alterou prompt, contrato de ferramenta, política, guard, instalador ou workflow.

A suíte inicial passou 1.069/8 ignorados, porém emitiu sete avisos de falha na decodificação de saída do PowerShell. A reprodução com esses avisos tratados como erro produziu seis falhas nos casos do guard local; o sétimo aviso vinha do teste de UI Automation com controles fictícios. A captura supunha UTF-8 mesmo quando o PowerShell escrevia em outra codificação. Agora stdout/stderr são preservados como bytes; os mesmos marcadores ASCII e códigos de retorno são exigidos. Não há `errors=ignore`, supressão de avisos ou retirada de asserções. Os 17 focados passaram depois, e a suíte final passou sem os avisos.

Primeira execução dos quatro cenários novos: dois passaram/dois falharam por erros da fixture — o modelo fictício tentava ler outro arquivo após a negação e o controlador tentava selecionar conversa antes do idle da carga. A fixture passou a responder a negação sem criar nova proposta e a esperar o estado real de idle. Critérios de persistência/negação não foram afrouxados. Segunda execução: quatro aprovados. Tentativas anteriores preservadas no JSON.

O primeiro CI completo [39137508131](https://github.com/Yamatosemj/aurenOFC/actions/runs/39137508131), no SHA `0f36396`, aprovou Linux (1.037/44 ignorados), mas Windows reprovou o teste novo de rotinas (1.080 aprovados/uma falha). O estado esgotado no banco ficou visível antes de o aviso ser publicado na fila da UI. O teste supunha observação atômica desses dois resultados assíncronos. A fixture agora força essa ordem com eventos controlados e espera estado e aviso separadamente; continua exigindo exatamente um aviso e ausência de repetição após reabrir. Não houve alteração de produção, aumento de timeout ou remoção de asserção para passar. Quatro integrados e a suíte local completa passaram novamente (1.073/8 ignorados, zero avisos, 72,54 s). O primeiro run e suas falhas permanecem registrados; o CI do novo HEAD é a referência para liberação.

## O que foi comprovado nesta etapa

1. **Caminho completo da interface à aplicação:** HTTP local exige token; worker padrão chama a fábrica real, Router e provider; somente o transporte do SDK é simulado. Não há chave ou chamada paga.
2. **Planejamento e persistência:** objetivo com duas leituras reais de TXT fictícios produz plano e passos; pausa salva; fechamento libera o banco; outro worker/fábrica recarrega e retoma o mesmo objetivo/chat.
3. **Verificação de resultado:** após retomar, a primeira leitura não se repete; códigos e soma 18 correspondem ao conteúdo real dos arquivos; resposta candidata é comparada às evidências; orçamento acumulado é mantido.
4. **Permissões:** política CONFIRM copiada pela fábrica exige negação explícita na UI/HTTP; nenhuma leitura bem-sucedida ou conteúdo do arquivo; tarefa termina em falha.
5. **Rotinas:** lembrete fictício nasce em rascunho, exige autorização separada, ocorre uma vez sem modelo e permanece esgotado após fechar/reabrir, sem repetição. Testes existentes cobrem rotinas executáveis, limites, escopo, revogação e expiração com efeitos simulados.
6. **Falha de armazenamento:** banco fictício corrompido provoca erro na interface, sem modelo, sem substituir dados por histórico vazio e sem alterar o arquivo.
7. **Interface real isolada:** oito controles aprovados no Chromium de teste com sandbox e widgets Tk reais (janela retirada): texto sem executar HTML, retomada, rotina em rascunho/revogação, confirmação negada, progresso/pausa, JavaScript sem erro, reabertura e cancelamento. Modelo e efeitos de dispositivo simulados.

Os testes entre processos, efeitos incertos, anti-loop e regressões anteriores também fazem parte da suíte completa desta candidata. Não somar os quatro cenários ou oito controles à contagem total como se fossem conjuntos independentes.

## O que bloqueia ou limita a integração

**Nenhum conflito de Git ou falha funcional foi identificado na bateria local final.** A liberação técnica depende também de ambos os jobs finais Windows/Linux aprovados no HEAD publicado; seus resultados devem constar na PR. A revisão humana das alterações e a decisão de integrar à main continuam com o proprietário. Não há merge automático nesta preparação.

Para uso cotidiano com dados pessoais ainda faltam avaliação humana do Windows instalado, aparência/DPI/foco/teclado, cenários reais do proprietário, perda de rede e execução de horas/dias. Cancelamento continua cooperativo; não desfaz efeitos já executados. Banco continua em texto e separado da memória conversacional. Rotinas dependem de aplicativo aberto e conversa selecionada. Estes são limites existentes, não funcionalidades novas ou promessas desta etapa.

**Não foram feitos novos testes Live pagos, ações pessoais, abertura de executável real, voz/hardware ou migração de banco pessoal.** As chamadas reais da etapa anterior permanecem históricas, sem reaproveitar autorização/orçamento para novos gastos. Os testes locais usam fontes copiadas, perfil/HOME/TEMP fictícios, credenciais retiradas e supervisor Windows. Nenhum .env, banco ou log pessoal foi aberto. Linux será validado no runner hospedado; não há alegação de Linux local neste PC Windows.

## Como testar a candidata

Use uma pasta nova com os arquivos desta branch, mantendo a instalação atual intacta. [Roteiro simples de teste no Windows](TESTE_MANUAL_WINDOWS.md). Será preparado um ZIP somente com arquivos versionados; SHA e checksum serão registrados na PR. O ZIP não instala dependências e não é instalador ou versão distribuída de produção.
