# Etapa 2A: cabecalho e inatividade da interface

Candidata local baseada na PR #172, SHA `48717bb68fd3545d31aa33028261fa33f9f50177`, sem merge ou atualizacao da instalacao pessoal. Escopo limitado a dois defeitos da etapa 2; nenhuma mudanca de permissoes, contratos, Dispatcher ou Harness.

## Causas e correcoes

- **E2-001:** a resposta de envio alterava `modoAtual` antes do polling, sem atualizar o cabecalho Ativo. O polling entao nao identificava transicao. O modo ativo e seu cabecalho agora sao aplicados juntos pelo polling; o retorno Desligado continua imediato. A resposta exibida e preservada nas duas ordens de chegada HTTP.
- **E2-002:** o `finally` da consulta de rotinas emitia `idle` mesmo sem trabalho iniciado. O servidor interpretava esse evento como fim de atividade e renovava seu contador continuamente. Agora a consulta emite `idle` somente se publicou `busy` para uma execucao real. Trabalho iniciado ainda termina com `idle`, inclusive em erro.

Inatividade, tarefa ocupada e confirmacao pendente foram separados nos testes: agenda sem rotinas nao renova o contador; tarefa nao terminal mantem `busy`; confirmacao pendente impede Standby sem simular atividade. O timeout e suas guardas nao foram alterados. Standby continua preservando sessao e nao representa pausa de ferramenta.

## Regressao e evidencias

`tests/test_chrome_mode_sync.py` executa as funcoes JavaScript de producao em Node com DOM minimo e ordem de respostas controlada. Cobre Desligado/Standby para Ativo, resposta preservada e Desligado imediato. `tests/test_worker_idle_polling.py` cobre inatividade, tarefa ocupada, confirmacao pendente e balanceamento busy/idle de trabalho bem-sucedido ou falho.

Antes das correcoes: **5 failed, 4 passed** nas nove regressoes, com falhas de cabecalho, contador renovado e busy apagado. Depois: **9 passed**. O primeiro ensaio teve um double incompleto de scheduler; foi corrigido antes da medicao comparativa, sem alterar producao.

Bateria ampliada: **86 passed**, incluindo as regressoes, testes da etapa 2, sintaxe JavaScript, confirmacoes e politica de permissoes. A selecao original da etapa 2 tambem foi repetida: **25 passed**. Integracao com fabrica/Harness reais e provider simulado passou conversa, cancelamento, timeout/recuperacao, nova sessao e fechamento durante processamento. Tk real foi exercitado com janela oculta.

Chromium headless observou Standby apos 119,94 s de espera desde a captura da resposta (timer original de 120 s), sem estimular o relogio. Cabecalho e backend coincidiram em todas as oito capturas; reativacao, botao Cancelar, desligamento e nova sessao passaram. Sem erros de pagina ou pedidos externos observados. Worker e servidor pararam, managers fecharam e socket foi liberado.

SHAs finais, JUnit, logs, capturas e roteiro reproduzivel constam no relatorio de entrega externo `C:/Users/victo/auren-etapa1-20261020/etapa2a/RELATORIO_ETAPA2A.md`. Dados e perfis usados sao descartaveis. Nenhuma chamada de modelo real ou automacao pessoal foi autorizada/executada.

## Limites

Esta validacao isolada nao aprova foco, DPI ou usabilidade de janela visivel. Cancelamento continua cooperativo; nao comprova interrupcao forcada de servico bloqueado. CI do novo commit nao foi disparado; o CI anterior da #172 nao e aprovacao desta candidata. Sem publicacao, merge ou etapa 3.
