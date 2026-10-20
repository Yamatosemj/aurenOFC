# Validacao da PR #173

PR continua **draft, sem recomendacao de merge ou rollout**. O roteamento foi
reforcado, mas o teste com API real reproduziu selecoes piores que a base.
Sucesso offline de disponibilidade de schemas nao comprovou sucesso do modelo.

## Escopo e autorizacao

- Base comparada: PR #172, `48717bb68fd3545d31aa33028261fa33f9f50177`.
- Prototipo original: `0c5e7ab2ca2871420ed944b3822828197fe39c4d`.
- Correcao de runtime final: `ca8af5224d766a3bcf67f9bacf900c034ed4ac54`.
  Evidencias apontam os SHAs efetivamente usados; commits documentais posteriores
  nao representam uma nova execucao paga.
- [Autorizacao especifica de API, teto agregado US$ 0,50](https://github.com/Yamatosemj/aurenOFC/pull/173#issuecomment-6280094151).
  Esta rodada da #173 tem ledger proprio; nao reutilizou nem apagou os registros
  das rodadas anteriores da #172.
- Copias isoladas `auren-pr173`, `auren-pr173-baseline`, `auren-pr173-original`.
  Sem alteracao de main, instalacao pessoal, secrets, workflows ou permissoes.
  Nao houve merge nem execucao de navegador/desktop real. Pytest usa fixtures
  temporarias; a API usa somente texto sintetico e handlers em memoria.

## Achados e correcoes

1. **Busca cortava tarefas compostas.** A rodada apos descoberta substituia os
   dominios originais pelos resultados. Agora conserva a uniao e disponibiliza
   busca em rotas especializadas. Uma falha antiga de contrato nao esconde um
   resultado de busca valido posterior. Custo: mais schemas nessas rodadas.
2. **`call_id` sozinho era insuficiente.** Agora ha correspondencia unica,
   ordenada e recalculo do resultado lexical com os argumentos da chamada.
   Nomes registrados injetados, descricao alterada, IDs duplicados, argumentos
   invalidos, output sem chamada, confiabilidade negativa e erros fecham a busca.
   Isso valida metadados, nao autentica objetos Python arbitrarios nem concede
   permissao. Nenhuma ferramenta nova e criada a partir do payload.
3. **Contaminacao do objetivo.** No modo opt-in, o texto do primeiro bloco do
   usuario e separado dos objetos SDK/resultados; conteudo externo nao escolhe
   dominios. O caminho legado continua igual sem a flag.
4. **Continuidade.** Schemas da chamada SDK anterior sao conservados na rodada
   seguinte, sem estado global por tarefa/chat. Continua nao existindo memoria
   permanente de todos os schemas descobertos; etapas distantes podem pesquisar
   novamente. Reuso do mesmo Router nao propaga descobertas entre tarefas.
5. **Audio ambiguo.** "proximo", "anterior", "play", "pausa" e "retoma" deixam
   de executar localmente com a flag. Play/pause e toggle, nao prova de pausa.
   Comandos explicitos de volume/mudo e proxima musica/musica anterior/parar musica
   continuam usando o Dispatcher. O comportamento antigo sem flag permanece.
6. **Metadados nao cumprem uma acao.** O Harness falha com
   `discovery_action_not_executed` quando so houve busca e o modelo tenta finalizar
   um objetivo de acao reconhecido. A heuristica nao reconhece toda a linguagem
   natural: permanece uma limitacao, nao uma verificacao semantica universal.
7. **Lexico e fallback.** Sinonimos de localizar/buscar e plurais foram alinhados;
   zero resultados informa ausencia de capacidade. A descricao da busca pede
   preservacao de alvo, esclarecimento e proibe inventar interfaces. **Isso nao
   resolveu a selecao Live**, como mostram os resultados abaixo.

Dispatcher, contratos, `scope_allows`, revisao de intencao, PermissionManager,
confirmacoes, cancelamento, limite de modelo e verificacoes posteriores foram
preservados. Tests exercitam recusa por escopo e permissao, contrato invalido,
busca repetida limitada e falsificacao. A busca nao aumenta `actions_executed`.
Sem segundo executor nem modelo auxiliar novo. Os revisores existentes continuam
disponiveis e seriam contabilizados pelo mesmo transporte.

## Testes offline

Ambiente local: Windows, Python 3.13.15, SDK OpenAI 3.15.0. O SDK local difere do
pin usado pelo CI; nao houve instalacao global. Todos os comandos pytest locais
foram executados por `py -3.13 scripts/diagnosticos/offline_python.py`, que remove
credenciais dos filhos e bloqueia sockets externos de Python. Nao e sandbox de SO.

| Execucao | Resultado |
| --- | --- |
| `-m pytest -q tests/test_dynamic_tool_discovery.py`, antes de corrigir, flag off e on | 2 passed em cada modo |
| Router, fast paths, discovery boundaries, paid budget, execution single path e contratos | 81 passed |
| Discovery + boundaries + budget + Dispatcher + permission policy, flag off e on | 41 passed em cada modo |
| Suite completa apos correcoes de runtime iniciais | 1295 passed, 8 skipped, 101,92 s |
| Suite completa no runtime final ca8af52 | 1295 passed, 8 skipped, 98,74 s |

Os oito skips locais sao testes de symlink sem privilegio WinError 1314. Nao
foram tratados como aprovados. Harness/Router/Dispatcher/PermissionManager e
cancelamento tambem fazem parte da suite completa.

Registro de tentativas: o alias `python` apontava para a Microsoft Store, entao
foi usado `py -3.13`; uma selecao de testes citou um arquivo inexistente e nao
coletou testes. Uma suite durante a edicao terminou 1266 passed/8 skipped/1 failed
porque o teste antigo ainda criava a chamada de busca sem argumentos. Foi
descartada como evidencia final e repetida. No modo opt-in uma assercao legada
fixava 49 ferramentas; agora exige 49 contratos legados, presenca da busca
exatamente quando habilitada e igualdade completa com os handlers. Nao houve
relaxamento do contrato ou de politicas para tornar o teste verde.

## Matriz de 100 prompts

[Script reproduzivel](../../scripts/diagnosticos/discovery_eval.py), com 20 prompts
por classe: conversa, comando evidente, composto, continuacao, ambiguidade/fora
do catalogo. Os JSONs incluem cada prompt sintetico, ferramentas exigidas, schemas
enviados, caracteres, estimativa de tokens, tempos e resultados por caso.

**Metodo:** disponibilidade = ferramentas exigidas presentes no toolset OU no
plano local (que nao foi executado). Rotulagem manual para 40 casos; os outros 60
medem abstencao local e schemas, nao uma taxa semantica de acerto. Quando falta
uma ferramenta e ha busca, simula-se UMA consulta lexical usando o prompt inteiro
como oracle. Essa consulta nao prediz o que o modelo perguntara. Tokens estimados
= `ceil(caracteres JSON/4)` por prompt, sem tokenizer; nao sao tokens faturados.
Tempos sao mediana de 11 selecoes aquecidas, sem rede; sujeitos a ruido local.

| Medida, soma de 100 prompts | Base #172 | #173 original ligada | Proposta ligada |
| --- | ---: | ---: | ---: |
| Caracteres de schemas iniciais | 1465159 | 267220 | 319144 |
| Tokens estimados de schemas | 366348 | 66825 | 79806 |
| Disponibilidade inicial (40 rotulados) | 39/40 | 38/40 | 39/40 |
| Disponibilidade apos ate uma busca simulada | 39/40 | 39/40 | 40/40 |
| Buscas simuladas necessarias | 0 | 1 | 1 |
| Efeitos locais indevidos, 80 casos fora de comandos simples | 0 | 6 | 0 |
| Mediana de roteamento local, ms | 0,1118 | 0,09195 | 0,12025 |

Artefatos: [base](pr173-evidence/baseline.json),
[original](pr173-evidence/original.json), [proposta](pr173-evidence/proposed.json),
[proposta sem flag](pr173-evidence/proposed-flag-off.json).
Sem a flag, os 100 resultados coincidem com a base em todos os campos exceto
tempo. A proposta envia mais schemas que o prototipo original para preservar
dominios e oferecer recuperacao. Nao derivar economia em dolares, cache hit-rate,
latencia de API ou sucesso de tarefas dessa matriz.

As continuacoes isoladas nao comprovam resolucao de anafora com contexto real.
Casos de reutilizacao do Router, contexto controlado, ausencia de referencias e
injecao foram testados offline; o uso composto/anforico com modelo continua
pendente. A reducao lexical nao garante que "o segundo" tenha alvo seguro.

## API real, efeitos sinteticos

[Runner](../../scripts/diagnosticos/discovery_live.py) usa o provider, Router,
Harness, Dispatcher e PermissionManager reais. TODOS os handlers terminais sao
substituidos antes do modelo; apenas a busca lexical continua real. A unica
consulta operacional permitida e uma listagem ficticia de duas janelas, com
titulos sinteticos. O escopo recusa qualquer outra ferramenta antes de executar.
Revisores existentes sao injetados, mas esses cenarios nao chegaram a exigir
revisao semantica paga de uma acao mutante. Nao se alega validacao Live disso.

| Caso | Base: chamadas / segundos / resultado | Proposta: chamadas / segundos / resultado |
| --- | --- | --- |
| Saudacao | 1 / 4,371 / completed | 1 / 2,237 / completed |
| "Mostre os titulos abertos" | 1 / 3,053 / listagem sintetica correta | 2 / 4,234 / scope denied |
| Teletransporte fora do catalogo | 1 / 3,211 / scope denied | 2 / 14,318 / scope denied |
| Titulos dos aplicativos visiveis no computador | 1 / 2,954 / listagem sintetica correta | 2 / 4,270 / scope denied |

Na primeira falha a consulta do modelo inventou "abas abertas no navegador";
na segunda consulta fora do catalogo inventou um controle de teletransporte na
interface. A descricao da busca foi reforcada, e o ultimo caso foi executado
no runtime final `ca8af52`: ainda pediu captura de tela, apesar de
`listar_janelas_windows` estar entre os schemas. A protecao de escopo impediu a
execucao; a falha funcional continua. Nenhuma permissao foi ampliada para aprovar
o experimento. Nao houve nova tentativa paga de teletransporte apos `ca8af52`.

Uma amostra por caso, cache compartilhado e ordem sequencial: **nao comprova
ganho geral de latencia/custo**. Inclusive, no primeiro pedido de titulos a
proposta gastou 7102 tokens de entrada em duas chamadas versus 6624 na base,
apesar de iniciar com apenas 696 caracteres de schema contra 24185. Reduzir a
primeira chamada nao assegurou economia total. O ultimo runtime inicia com 940
caracteres devido ao esclarecimento adicional da descricao.

## Ledger pago e encerramento

[Ledger sem prompts ou chaves](pr173-evidence/paid-budget.json) e
[resultados sanitizados](pr173-evidence/live-results.json). Respostas livres e
logs locais nao foram publicados. Modelo solicitado e retornado:
`gpt-5.6-luna`; `reasoning=none`, `service_tier=default`, sem hosted tools,
sem `previous_response_id`, SDK sem retry automatico.

- 11 chamadas totais, todas com usage recebido; 0 falhas de transporte/uso desconhecido.
- 47833 tokens de entrada; 308 de saida; 18943 cached; 28857 cache write;
  0 reasoning tokens reportados (ja incluidos no teto de saida se existissem).
- Custo estimado reconciliado por usage: **US$ 0,00796931**.
- Reserva conservadora acumulada, nunca devolvida ao saldo: **US$ 0,4224**.
- Teto agregado **US$ 0,50**. Rodada **encerrada** apos reproduzir a regressao;
  o saldo aritmetico nao e instrucao para continuar gastando.
- Estimativa nao equivale a fatura confirmada: `billing_confirmed=false`.

Tarifas verificadas antes das chamadas na [documentacao oficial de GPT-5.6
Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna): US$ 0,20/M
input, US$ 0,02/M cached, US$ 1,20/M output; cache writes a 1,25x input =
US$ 0,25/M. O custo separa essas categorias, sem desconto ficticio.
Cada chamada reserva antes da rede ate 60000 tokens de entrada a US$ 0,60/M e
o teto de saida a US$ 3/M, cobrindo o raciocinio. Payload UTF-8 +8192 limita a
entrada, sem imagens/audio; bounds/usage inconsistentes bloqueiam novas chamadas.
Uso desconhecido conserva a reserva e interrompe todo gasto. Os testes offline
exercitam o teto compartilhado, restart, falha, usage ausente e requests fora do
escopo; nao sao alegacoes de cobranca real desses erros.

## CI e pendencias

O workflow automatico filtra PRs para main; esta PR e stacked sobre a #172.
Foi acionado somente o workflow manual hospedado existente, sem editar YAML ou
disparar runner pessoal. [Run de codigo inicial b767fa4](https://github.com/Yamatosemj/aurenOFC/actions/runs/39346580390):
Linux **1258 passed /45 skipped**; Windows hospedado **1302 passed /1 skipped**.
CI do HEAD documental final deve ser consultado na descricao da PR.

Bloqueios reais: selecao do modelo apos busca; capacidade fora do catalogo;
continuidade composta e anafora com API; avaliacao maior e contrabalanceada.
Sem testes fisicos Windows/browser/voz, sem instalacao pessoal, sem rollout.
O merge continua pendente e nao e recomendado por esta validacao.
