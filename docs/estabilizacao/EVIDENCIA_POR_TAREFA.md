# Conclusão com evidências da própria tarefa

Base: PR #163, `38e3413e393c9cc981212e44807ee119496ac691`.
Branch isolada: `estabilizacao/evidencia-por-tarefa-20261018`.
Sem alteração da main, Electron, ferramentas novas ou identificação de
capacidades indisponíveis. Os lembretes pelo chat continuam fora desta etapa.

## Causa confirmada

O contexto guardava resultados e respostas anteriores do mesmo chat. Eles já
eram rotulados como dados históricos, mas esse rótulo não impedia que o modelo
reutilizasse o texto. Na execução real da #163 houve uma chamada nova ao modelo,
não um acerto do cache local: a resposta repetiu o conteúdo anterior sem leitura.

Três condições permitiram persistir `completed`:

1. O filtro inicial reconhecia alguns imperativos, mas não “leia” nem consultas
   como “qual o conteúdo do arquivo?”. Assim, não exigia ferramenta na entrada.
2. O plano era simples, de uma etapa. Complexidade estimava tamanho do trabalho,
   mas estava sendo usada implicitamente como indicação de que uma resposta
   puramente textual bastaria.
3. A revisão de conclusão era obrigatória para planos compostos e efeitos
   executados. Com uma etapa de leitura **e zero ferramentas**, ela não rodava.
   O texto final podia chegar diretamente a `TaskManager.complete`.

O aviso `unverified` da #163 reduzia o dano na notificação, mas não corrigia o
estado da tarefa no Harness. Esta mudança impede a conclusão indevida antes
da publicação da resposta de sucesso, gravação de estratégia bem-sucedida e
persistência de `completed` nesse caminho.

## Correção

`core/task_evidence.py` identifica pedidos reconhecíveis de acesso ao ambiente,
separadamente da complexidade do plano. A finalização normal e a conclusão
local consultam os passos da tarefa atual. Uma resposta anterior, um histórico
de outro objetivo ou uma consulta sem relação com o pedido não valem como prova.

Para leituras de arquivos com caminho explícito, exige uma leitura bem-sucedida
do alvo solicitado. Aceita equivalência lexical de caminho relativo/absoluto,
sem abrir arquivos para classificar evidência. Uma listagem de abas não prova
o conteúdo de uma página; uma listagem de janelas não comprova maximização.
Os verificadores existentes de efeitos e tarefas compostas continuam ativos.

Pedidos explícitos de leitura de arquivo já orientam a primeira chamada com
`tool_choice=required`. Isso não autoriza ferramenta: revisão de intenção,
Dispatcher, PermissionManager e escopo continuam independentes. O controle
final também recusa uma resposta sem prova caso o modelo ignore a orientação.
Não foi criada nova chamada de revisão de IA para cada leitura simples.

Explicações, cálculos, texto fornecido pelo usuário e resumos explicitamente
retrospectivos podem continuar sem ferramenta. Uma pergunta legítima de
esclarecimento permanece visível e pendente, sem afirmar que a leitura ocorreu.
O contexto continua disponível para esses diálogos; não foi apagado para fazer
o teste passar. O estado enviado ao modelo agora distingue explicitamente
contexto antigo de passos comprovados desta mesma tarefa.

Checkpoints da **mesma tarefa** preservam suas observações. O controle não
obriga repetir essas leituras, não restaura aprovações e não altera a proteção
contra repetir efeitos ou retomar uma execução incerta. Não houve migração de
banco, novo estado de tarefa, alteração de permissões ou aumento de limites.

## Evidências offline

- Antes da correção: **16 falhas e 10 aprovações**. Os testes reproduziram
  respostas antigas aceitas como conclusão, inclusive em arquivos, navegador
  e Windows, com e sem banco persistente.
- Bateria final focada: **89 aprovações**, incluindo continuidade, notificações,
  permissões, rotinas, orçamento e resistência a retomadas incertas.
- Suíte completa local Windows/Python 3.13: **1.141 aprovações, 8 ignorados,
  nenhuma falha**, em 81,82 s. Ignorados: casos existentes de symlink sem
  privilégio. Exceções de threads foram tratadas como erros. Perfil fictício,
  cópia somente de fontes, sem credenciais e sob watchdog.
- As ferramentas de navegador e Windows nos novos testes têm efeitos fictícios.
  O Harness, seus estados e a persistência são reais. Há casos positivos, falta
  de ferramenta, ferramenta sem relação com o pedido, arquivo errado, permissão
  negada, conteúdo de página não observado e checkpoint próprio válido.
- A regressão da #163 foi fortalecida: a tarefa que antes ficava `completed`
  agora precisa ficar `failed`, assim como a rotina/aviso. O fallback antigo
  `unverified` permanece para casos não reconhecidos pelo controle local.

Falhas intermediárias preservadas: a primeira bateria ampliada teve 93 passes
e uma falha na expectativa antiga de `unverified`, atualizada para exigir falha
no próprio Harness. A primeira suíte completa teve **1.138 passes, 1 falha e 8
ignorados**: a recusa de conclusão escondia a pergunta de esclarecimento do
fluxo “abrir aplicativo → pergunta → sim”. Corrigida a apresentação da pergunta;
os critérios de execução, permissões e conclusão não foram enfraquecidos.

Os resultados numéricos, hashes e tentativas constam de
[offline-results.json](evidencia-por-tarefa/offline-results.json).

## Live autorizado

Foram usadas apenas as **3 chamadas restantes** da autorização anterior de
US$ 0,50/8 chamadas. O controle existente foi retomado explicitamente, mantendo
as cinco chamadas e o consumo da #163. O padrão continua recusando sobrescrever
um controle existente; a continuação validou modelo, limites e reservas e não
zerou contadores. SDK sem repetição automática, saída limitada e reserva
conservadora persistida antes de cada requisição.

Modelo: `gpt-5.6-luna`. Fábrica, provider, Router, Harness, Dispatcher,
PermissionManager, RoutineScheduler e TaskManager reais, com arquivo e perfil
fictícios. Sem aprovação automática: qualquer confirmação seria negada; o
escopo da rotina autorizava somente a leitura exata do arquivo de teste.

1. Uma leitura real inicial, sem IA, gravou `CODIGO_ANTIGO: 19 itens.` como
   tarefa e conversa anteriores. O arquivo foi então alterado para
   `CODIGO_NOVO_K84: 23 itens.`. A rotina, com o resultado antigo no contexto,
   executou uma nova leitura pelo Dispatcher e só depois ficou `completed`.
   A resposta apresentou o código novo e 23 itens. **Passou, 2 chamadas**.
2. Um pedido para resumir o conteúdo recém-lido, sem novo acesso ao arquivo,
   foi respondido corretamente com 23 itens. Ficou `completed` sem passo de
   ferramenta, pois era diálogo retrospectivo. **Passou, 1 chamada**.

Os estados persistidos foram reabertos e comparados. Consultar os avisos e
chamar novamente o tick de uma rotina esgotada não repetiu o acesso nem chamou
o modelo. Nenhum arquivo pessoal, aplicativo do Windows ou navegador pessoal
foi acessado. Nenhum cenário pago foi repetido para obter aprovação.

Resultado desta etapa: **2 cenários passaram, nenhum falhou**. As duas falhas
pagas da etapa anterior continuam nos registros da #163, sem reclassificação.
Uso novo: **18.733 tokens de entrada, 88 de saída, 6.972 de leitura de cache
e 11.633 de gravação de cache**; os campos de cache são parcelas da entrada.
Custo novo estimado: **US$ 0,00317889**. Acumulado: **US$ 0,00587470**;
reserva preventiva acumulada: **US$ 0,3072**, ambos dentro de US$ 0,50.
Foram esgotadas as **8/8 chamadas**; não há saldo de chamadas para novos Live
nessa autorização. Estimativas não representam fatura confirmada.

[Resultado Live original](evidencia-por-tarefa/api-results.json) e
[consumo acumulado por chamada](evidencia-por-tarefa/api-budget.json), incluindo
tokens de entrada, saída, leitura/gravação de cache e fonte das tarifas.

## Limitações e pendências

O reconhecimento local é conservador e cobre formas de pedido verificadas nos
testes, não toda formulação possível em linguagem natural. Uma frase ambígua
pode exigir reformulação. Comparação lexical de arquivos pode recusar aliases
equivalentes que precisariam de resolução de symlink, deliberadamente não feita
durante a classificação. Não elimina o risco de o modelo interpretar ou resumir
mal um resultado realmente obtido; revisão semântica continua obrigatória nos
caminhos compostos/de efeitos existentes.

Não se tratou identificação de capacidades indisponíveis, lembretes pelo chat,
Router/fallback de 49 ferramentas, desempenho, Electron ou novos recursos.
Navegador e Windows tiveram respostas/efeitos simulados; o Live real desta
etapa cobriu arquivo temporário e conversa retrospectiva. Não houve automação
do desktop pessoal, voz, hardware, navegação externa ou validação por horas/dias.
