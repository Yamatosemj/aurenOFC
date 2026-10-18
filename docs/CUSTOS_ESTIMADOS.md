# Uso e valores de referência

Os tokens registrados vêm da resposta do provedor quando ela informa esse uso. Se uma consulta ao revisor falha antes de receber o uso, a tentativa e sua duração são registradas, com uso desconhecido; não se inventa uma quantidade faturada. Uma resposta inválida que informou tokens continua entrando na contagem da tarefa.

Os contadores exibidos no terminal somam o processo inteiro. Para uma tarefa específica, consulte seu rastro. Tentativas que falham não equivalem a chamadas gratuitas ou faturadas: sem resposta de uso, isso permanece desconhecido.

É possível configurar tarifas por identificador de modelo na variável `AUREN_MODEL_PRICES_JSON`. Cada entrada precisa de `input`, `cached`, `cache_write` e `output`, em dólares por milhão de tokens. As quatro tarifas devem ser números finitos e não negativos. Um exemplo com valores **fictícios**, somente para mostrar o formato:

```json
{"modelo-ficticio":{"input":2,"cached":1,"cache_write":3,"output":4}}
```

O identificador informado na resposta do provedor tem preferência sobre o modelo configurado. Sem tarifa válida para ele, o sistema preserva os coeficientes históricos somente como `referencia_generica_nao_fatura`. Os rastros e o relatório de métricas indicam essa base. Os valores não são uma tabela atual de preços, cobrança, saldo ou fatura; conferir tarifas é responsabilidade de quem as configurar. Não foram consultados preços nem executada API paga nesta manutenção.

Relatórios de logs antigos sem modelo informado usam a configuração atual como referência e não reconstituem com garantia uma cobrança passada. Somar tarefas não representa isolamento de faturamento da conta.
