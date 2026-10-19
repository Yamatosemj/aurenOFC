# Validacao Live de latencia ? 19/10/2026

Candidata sobre a PR #171; nenhuma integracao na main nem atualizacao da instalacao pessoal. Testes com API real, gpt-5.6-luna, SDK instalado 3.15.0 (pin do repositorio: 3.26.0). Sem alteracao global de dependencias. Harness, Router, Dispatcher, contratos e PermissionManager reais; perfil Chromium novo e janela Tk sintetica. Nao foi usado perfil pessoal.

## Resultado e comparacao

| Operacao | Historico recebido | Live atual | Resultado |
|---|---:|---:|---|
| Saudacao | 14 s | 2,875 s; 1 chamada | aprovado |
| Maximizar janela | 10 s | 4,592 s; 2 chamadas | aprovado; IsZoomed independente |
| YouTube | 60 s | tentativas abaixo | nenhuma conclusao ponta a ponta aprovada |
| Abrir Bloco de Notas | 47 s | nao repetido | so descoberta medida na etapa anterior |
| Pesquisa generica no navegador | sem baseline separado | nao repetida | nao validada separadamente |

Tempo interno de ferramentas: saudacao 0 ms; maximizar 21,467 ms. No YouTube, 2,95?5,13 s por tentativa, contra 13,07?37,39 s totais; o restante inclui modelo, revisoes e orquestracao. Contagens por tentativa, rodadas principais e soma das ferramentas constam no JSON sanitizado.

Amostras unicas, ambiente/objetivos diferentes do historico; nao sao medias nem prova de melhoria geral. Maximizar usa janela sintetica, nao arquivo pessoal. Saudacao e maximizar precedem os ajustes do navegador/revisor; nao foram repetidos no HEAD final.

## Tentativas completas, inclusive falhas

| Caso | Segundos | Chamadas API, incluindo revisores | Resultado |
|---|---:|---:|---|
| greeting-69bdc780 | 2.875 | 1 | aprovado |
| maximize-ebe72118 | 4.592 | 2 | aprovado |
| youtube-4c5fbc61 | 34.386 | 12 | limite local de rodadas do harness atingido |
| youtube-7542eddc | 13.069 | 5 | permission_denied |
| youtube-76188aa7 | 13.551 | 5 | esclarecimento; sem video |
| youtube-91abcf8d | 37.389 | 12 | completion_recovery_exhausted |
| youtube-a2410389 | 34.952 | 16 | browser_verification_missing |
| youtube-c90160aa | 32.842 | 14 | completion_verification_failed |
| youtube-cb7636ba | 33.43 | 14 | completion_verification_failed |
| youtube-f94be4f9 | 25.143 | 10 | limite local de rodadas do harness atingido |

A navegacao e o titulo coincidiram com o primeiro resultado observado em varias tentativas, mas isso nao basta para declarar tarefa aprovada. A ultima tentativa apresentou sugestao de busca diferente (lasanha de abobrinha) apos Enter, embora o preenchimento autorizado fosse literal. A verificacao de navegador recusou a conclusao. O runner passou a exigir tambem a consulta exata; os resultados antigos permanecem inalterados. Nao houve novo teste pago depois desta descoberta.

Duas tentativas atingiram o teto experimental de 8 rodadas; corrigido no runner para 12, default da producao. Uma falhou porque o canal de confirmacao do teste nao autorizava preenchimento/Enter; o escopo foi corrigido apenas para esta busca publica, sem mudar PermissionManager. A tarefa de esclarecimento aparece completed no estado legado; o runner corretamente a marca como falha por nao haver video. Esses defeitos do teste nao sao atribuidos ao produto.

## Causas comprovadas e correcoes

- O resultado do clique nao fornecia metadados suficientes para provar navegacao. ToolResult agora inclui alvo, indice, tipo, href e URLs antes/depois; a verificacao compara com leitura independente. Compatibilidade textual preservada. Nao valida semanticamente qualquer destino nem libera botoes/formularios.
- A URL do resultado estava depois do caractere 700 e era cortada no historico do revisor de intencao: o modelo solicitou URL ja observada. Limite aumentado para 2200, dois resultados, mantendo contexto delimitado como dados nao confiaveis.
- O revisor final omitia leituras posteriores da lista de referencias. Instrucao explicita exige referencias da mesma etapa. Falta de prova vira pendencia recuperavel uma unica vez no fluxo existente; referencias inexistentes continuam invalidas. Nenhuma referencia e inventada ou inserida automaticamente.
- A mesma resposta/evidencia foi aceita em auditoria isolada e recusada no fluxo completo: variabilidade observada do revisor, nao prova de causa unica. Experimento reasoning=low aceitou controle correto e rejeitou URL errada e falta de pos-leitura. A tentativa completa falhou antes da auditoria final; ajuste de producao revertido, mantendo none e modelo original.

Persistem falhas ponta a ponta do YouTube: guardas de navegador e referencias de prova. A sugestao selecionada por Enter precisa ser tratada genericamente por verificacao da consulta efetiva. Nao foram criados atalhos por aplicativo, segundo roteador ou bypass de autorizacao.

## Arquivos e regressao

Runtime: core/browser_verification.py, core/harness.py, core/intent_verification.py, core/task_verification.py, tools/browser_elements.py. Provider termina com comportamento original de raciocinio. Runner explicito: tests/live_latency_api.py. Regressao: test_link_navigation_evidence, test_intent_evidence_boundary, test_completion_proof_recovery, test_live_latency_budget e fixture Chromium offline. Lista completa no diff da PR. A fachada continua propagando o retorno nativo como nas demais ferramentas estruturadas; consumidores Python externos que esperavam string precisam usar .message. A mensagem e o envelope do Dispatcher permanecem compativeis.

Primeira suite completa: 1262 aprovados, 8 ignorados, 1 falha: teste direto antigo tratava ToolResult como string. Consumidores de runtime passam pelo Dispatcher, que ja aceita ToolResult; teste atualizado para mensagem e evidencia estruturada, sem alterar condicao de sucesso. Suite local final e CI: resultados na PR e evidencia JUnit local. Testes anteriores focados passaram (42 navegador/orcamento, 55 intencao/orcamento, 53 recuperacao/Harness). Nao confundir mocks/fixtures com testes pagos.

## Custo e controle

96 chamadas adicionais; 346032 tokens de entrada e 6169 de saida. Estimativa acumulada US$ 0.09391080; nao e fatura. Inclui tentativas malsucedidas e auditorias isoladas. Limite absoluto US$ 0,50. Exposicao conservadora final US$ 0,191523.

Tarifas verificadas: [pricing oficial](https://developers.openai.com/api/docs/pricing), [modelo](https://developers.openai.com/api/docs/models/gpt-5.6-luna). Estimativa trata toda entrada a US$0,25/M e saida US$1,20/M; ignora descontos. Reservas usam US$0,50/M entrada e US$3/M saida, limite de bytes + enquadramento, saida maxima 1200 e sem retries SDK. Reservas persistem antes de enviar. Uso desconhecido nunca libera saldo; uso conhecido e reconciliado conservadoramente. Soma historica de reservas reutilizadas excede US$0,50, mas nao representa gasto/exposicao simultanea. Ledger preserva todos os registros; nao foi reiniciado. Testes cobrem recusa antes da rede, reinicio, uso desconhecido e reconciliacao.

[Resultados sanitizados](evidence/live-20261019/results.json), [ledger sem prompts/credenciais](evidence/live-20261019/budget.json), [controles do revisor](evidence/live-20261019/review-low-controls.json). Logs detalhados e perfis sinteticos permanecem fora do repositorio em C:/Users/victo/auren-latencia-evidence/live-20261019; nao publicar esses perfis.

## Pendencias e recomendacao

Nao integrar como solucao integral de latencia. Revisar as PRs encadeadas separadamente e manter exigencia de prova; resolver genericamente consulta efetiva/pos-condicoes do navegador antes de novo Live. Corrigir estado legado de esclarecimento em trabalho separado. CI nao substitui validacao diaria com instalacao pessoal. Nenhum merge realizado; PR de seguimento e checks identificados na entrega.
