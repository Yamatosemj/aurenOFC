# Entrega de avisos — candidata baseada na PR #162

> Continuação sobre a #163: a conclusão indevida de leitura sem ferramenta foi
> corrigida no Harness em uma candidata separada. Consulte as
> [evidências atuais](EVIDENCIA_POR_TAREFA.md). As falhas Live abaixo preservam
> a execução anterior; a identificação de capacidades indisponíveis segue pendente.

## Escopo e bloqueios observados

Esta etapa mantém RoutineScheduler/TaskManager como única fonte. Não acrescenta
ferramentas de lembrete/timer pelo chat, não integra #137 inteira nem Electron.
Reaproveita o conceito de aviso persistido e confirmação visual da #137.

O primeiro teste Live autorizado encontrou dois problemas além da entrega:

1. Ao executar uma rotina de leitura, o modelo reutilizou a resposta de uma
   tarefa anterior sem chamar ferramenta. O Harness persistiu `completed` com
   zero passos. Isso é uma limitação da comprovação de tarefas simples e do
   contexto anterior; não é evidência de nova leitura. Não vamos reescrever o
   Harness nesta etapa. A proteção acrescentada ao scheduler registra o aviso
   como `unverified` e a rotina como `failed` quando não há nenhum passo de
   ferramenta bem-sucedido. O aviso diz “Resultado da rotina não comprovado”.
   Isso não corrige nem oculta o `completed` já persistido pelo Harness na tarefa.
2. Diante do pedido de lembrete pelo chat, o escopo seguro bloqueou a proposta.
   Não houve criação nem sucesso falso, mas a resposta falou em rotina não
   autorizada em vez de explicar a capacidade ausente. Não foi validado um
   reconhecimento correto dessa limitação. Descoberta de capacidades e a
   recuperação geral continuam pendências fora desta entrega.

Esses achados bloqueiam uma aprovação geral das decisões da IA. Os cenários
pagos que falharam não serão repetidos para obter resultado positivo.

## Resultados

### Simulados e componentes reais sem API

- Reprodução inicial: 5 testes falharam antes da implementação da persistência.
- Testes focados finais: 60 passaram. Incluem as regressões de continuidade
  da #162, permissões, controle de orçamento e composição real via HTTP.
- Suíte completa local Windows/Python 3.13: **1.106 passaram, 8 ignorados,
  nenhuma falha**, em 74,95 segundos. Os oito ignorados são os casos existentes
  de symlink sem o privilégio necessário. Avisos de exceções em threads foram
  tratados como erros. Código executável do commit
  `455aa908866b22d7eeaedc4da74affad2848c14d`; depois dele, só documentação/evidências
  foram atualizadas. CI hospedado deve ser conferido no HEAD final da PR.
- SQLite real: aviso sobrevive à reabertura; falhas de gravação revertem o
  consumo da ocorrência; confirmação com falha mantém o aviso pendente;
  adiamento invalida confirmação atrasada de uma versão anterior.
- Dois subprocessos reais terminam abruptamente com `os._exit`: após gravar
  lembrete pendente e após efeito fictício incerto. A reabertura conserva o
  aviso ou informa interrupção, sem repetir a execução.
- Chromium real isolado, sem API: **9 controles passaram**. Exibição visível,
  texto sem execução de HTML, falha de confirmação, recarga, Standby, adiamento
  de 10 minutos, reinício do servidor/worker, novo horário, identificação de
  resultado não comprovado, token obrigatório e isolamento de chat/sessão.
  Relógio controlado; a fixture do navegador aciona `tick` explicitamente. A
  consulta periódica do worker real é coberta no cenário HTTP de rotinas.
- A captura [avisos.png](evidencias/avisos.png) mostra a interface realmente
  renderizada. Isso comprova o cartão no navegador de teste, não leitura humana.

### Live com modelo real — sem repetição dos cenários

Provider, Router, fábrica `auren.criar_harness`, Harness, Dispatcher,
PermissionManager, TaskManager e SQLite reais. Perfil e arquivo fictícios.
Escopo adicional do teste permite somente ler/inspecionar esse arquivo;
confirmações solicitadas seriam negadas, nunca aprovadas automaticamente.

| Cenário | Resultado observado |
| --- | --- |
| Saudação real com “Como posso ajudar?” | Passou; nenhuma pendência indevida |
| Nova tarefa de leitura após a saudação | Passou; objetivo separado, código comprovado por ferramenta e estado persistido |
| Rotina executável com leitura autorizada | Falhou; modelo repetiu conteúdo anterior sem nova ferramenta e Harness concluiu com zero passos |
| Pedido de lembrete pelo chat | Falhou no reconhecimento da capacidade; bloqueado com mensagem inadequada, sem criação ou sucesso falso |

Total: **2 cenários passaram e 2 falharam**, em **5 chamadas** ao
`gpt-5.6-luna`. Entrada: 34.131 tokens; saída: 130; cache de leitura: 26.053;
gravação de cache: 8.063 (os campos de cache são parcelas da entrada).
Custo estimado: **US$ 0,00269581**. Reserva conservadora acumulada:
**US$ 0,192**, mantida mesmo após respostas conhecidas. Ambos inferiores aos
US$ 0,50 autorizados; 3 chamadas do limite de 8 não foram utilizadas.
Os preços usados estão registrados no [controle de consumo](evidencias/api-budget.json)
com a fonte da [documentação oficial OpenAI](https://developers.openai.com/api/docs/pricing).
Não representam fatura confirmada. Nenhuma chave consta das evidências.

As [evidências Live originais](evidencias/api-results.json) permanecem com as
duas falhas. A proteção `unverified` foi feita **depois** dessa execução,
reproduzindo a resposta observada em teste offline que primeiro falhou e depois
passou. Não houve segunda execução paga nem alegação de aprovação Live dessa
proteção final. A semântica geral de conclusão e descoberta de capacidades
continua pendente; esta entrega não está aprovada para uso autônomo geral.

### Falhas intermediárias preservadas

- Primeiro teste de navegador: a fixture bloqueava o processamento de rotas do
  Playwright enquanto esperava a confirmação. Corrigido o bombeamento do
  navegador na espera; não foram relaxados os critérios de exibição/gravação.
- Primeira bateria focada ampliada: 57 passaram e 1 falhou. A seleção de chat
  era observável antes do evento `idle`; pedir retomada nesse intervalo era
  corretamente recusado. A fixture agora exige chat selecionado **e** worker livre.
- Reprodução da falha Live por texto sem ferramenta: 1 teste falhou antes da
  proteção e passou depois. Não foi reclassificado como Live aprovado.

## Contrato de entrega

O novo registro `auren_routine_notifications` fica no **mesmo banco** do
TaskManager. Nenhum banco, singleton ou thread da #137 foi importado. Os
registros anteriores de rotinas permanecem intactos; uma base fictícia com o
esquema anterior foi reaberta e continuou funcionando sem nova autorização.

Para lembrete local, consumir a ocorrência e criar o aviso pendente são uma
única transação. Para rotina com ferramentas, a conclusão e o aviso são
gravados juntos; se houver queda durante o efeito, a recuperação informa
resultado incerto e não executa de novo. Avisos usam o ID da ocorrência,
separado do estado da rotina. A reentrega não chama Harness, Dispatcher ou API.

O Chrome consulta os avisos pendentes do chat selecionado. Aguarda renderização,
documento visível e cartão visível antes de confirmar essa versão do aviso.
Falha de conexão/confirmação deixa o registro pendente. “Adiar aviso 10 min”
altera apenas a entrega persistida, incrementa sua versão e impede que uma
confirmação atrasada descarte o aviso futuro. Não muda o horário da rotina,
não restaura autorização e não repete efeitos.

A entrega é **ao menos uma vez** até confirmação. Pode reaparecer após queda
entre a exibição e a confirmação. Não se promete notificação exatamente uma
vez, leitura humana, som, aviso nativo do Windows, email ou execução em segundo
plano com processo encerrado. Cartões já confirmados somem ao recarregar a
página; o recebimento fica persistido. Cartões ainda na página permitem adiar
ou dispensar. Uma tela oculta ou um cartão fora da área visível não é confirmado
automaticamente; mensagens longas podem exigir dispensar explicitamente.

## Aplicativo, sessão e reinício

| Situação | Comportamento |
| --- | --- |
| Ativo com chat selecionado | Worker verifica vencimentos quando ocioso; Chrome exibe pendentes desse chat |
| Standby | Worker continua habilitado; avisos são exibidos/confirmados na página visível |
| Tarefa longa ou pausada | Mantida a restrição anterior: não inicia outra rotina até estado terminal; pode atrasar novos disparos |
| Sessão desligada | Não consulta nem confirma avisos; pendências persistem para reativação e seleção do mesmo chat |
| Chrome fechado e servidor ativo | O worker pode produzir avisos; ficam pendentes até reabrir a página no chat correspondente |
| Processo encerrado | Não emite alertas; avisos já persistidos sobrevivem e reaparecem após carregar/selecionar o chat |

Não alteramos a expiração de rotinas: se um disparo ainda não ocorreu quando
seu prazo expira, ele não é executado retroativamente. Avisos **já produzidos**
não expiram junto com a rotina. Não é possível recuperar com certeza avisos
que a #161 já consumiu e perdeu antes desta mudança. Não usar uma versão antiga
para confirmar os novos avisos; ela desconhece esse protocolo.

## Como repetir sem consumir API

Em checkout isolado, com perfil fictício e sem credenciais:

```powershell
py -3.13 -m pytest tests/test_routine_notifications.py tests/test_notification_live_budget.py tests/test_followup_stabilization.py tests/test_integration_consolidated.py -q
py -3.13 -m remote_tests.notification_ui_smoke --artifacts CAMINHO_TEMPORARIO_NOVO
```

O segundo comando precisa de Chromium de teste instalado e configurado em
`PLAYWRIGHT_BROWSERS_PATH`. Não usar perfil do Chrome pessoal. O script Live
é manual, exige autorização explícita por variável, ambiente isolado e um
controle de consumo novo aprovado; não é coletado pelo pytest ou CI. A
autorização de US$ 0,50 deste ciclo não se renova ao executar o script novamente.

## Ainda não validado

Uso por horas/dias, suspensão/hibernação do Windows, falha física do disco,
notificações com processo encerrado, aparência em outros tamanhos/DPI,
entrega/confirmacão durável no Tk e ferramentas de lembrete/timer pelo chat.
Não houve testes em arquivos pessoais, aplicativos sensíveis, voz ou hardware.
