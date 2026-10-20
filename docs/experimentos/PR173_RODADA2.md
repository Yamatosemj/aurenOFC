# PR #173 — investigacao e segunda rodada independente

**Decisao: manter a base #172 como referencia de uso, com descoberta desligada.**
O bootstrap experimental melhorou algumas escolhas e a continuidade na amostra,
mas nao atingiu o criterio conjunto de confiabilidade e menor custo total.
Nao recomendo substituir a base, fazer merge ou habilitar na instalacao pessoal.
A PR permanece draft. As alternativas e falhas estao preservadas, inclusive
quando contrariam a proposta.

Esta e a nova autorizacao da sessao de 20/10/2026: **US$ 0,50 adicionais no total**,
independentes da [primeira rodada](PR173_VALIDACAO.md). O ledger anterior nao foi
reaberto nem teve valores removidos. A nova rodada foi encerrada e bloqueada para
novas chamadas em **176 chamadas / US$ 0,05158722 estimados**.

## 1. Versoes e condicoes

| Papel | SHA | Configuracao |
| --- | --- | --- |
| Base #172 | `48717bb68fd3545d31aa33028261fa33f9f50177` | descoberta desligada |
| #173 no inicio desta tarefa | `6a0ed947b8b02101f5bf6d82b8e3fbe950d5e78f` | descoberta ligada, politica anterior |
| Bootstrap v1 | `924e9709c28ebc8f6476228c61130e7bad1f524b` | consultas frequentes junto da busca |
| Bootstrap v2, runtime final | `87b474031f7c220b3d8cfc1ed7d4728f2cb8dc28` | v1 e ancoras de outros dominios adiadas |
| Codigo de testes/ledger final | `09dc184` | mesmo runtime; encerra ledger e audita resultados |

Windows, Python 3.13.15, SDK OpenAI local 3.15.0; o CI usa o pin 3.26.0 do
requirements, sem instalar ou substituir pacotes globais. Modelo solicitado e
retornado em todas as chamadas: **gpt-5.6-luna**, reasoning none, service tier
default, store false, SDK sem retries. Mesmos dados sinteticos, prompt de sistema,
estado do Harness, contratos, permissoes e orcamentos por tarefa para as tres
versoes. A ordem das versoes foi rotacionada por caso/repeticao, sem concorrencia.

Os ensaios usam o Harness real com TaskManager em memoria e SessionContextManager,
Router, provider, Dispatcher e PermissionManager reais. Todos os handlers
terminais sao substituidos antes de consultar o modelo; apenas a busca de
metadados continua real. Uma scope function restringe os alvos/operacoes da
fixture igualmente nas versoes. Contratos, revisao de intencao, confirmacao e
guards continuam ativos; nenhuma permissao foi ampliada para aprovar um caso.

Os fast paths sao desabilitados **somente no runner comparativo e igualmente
para todas as versoes**, para medir o caminho do modelo, sem executar comandos
locais reais. Isso nao mede todo o desempenho do produto. Nao foram validados
UI, navegador, Windows real, hardware ou a revisao de conclusao do modo duravel.
Houve 7 chamadas pagas do revisor de intencao; nao houve chamada paga de revisao
de conclusao. Nenhum segundo modelo ou executor foi introduzido no runtime.

## 2. O que causava as regressoes

### A descoberta comecava sem uma capacidade suficientemente ancorada

Na politica anterior, um pedido sem dominio reconhecido recebe somente
`buscar_ferramentas`. O modelo precisa formular a busca antes de ter schemas
operacionais. Nos logs anteriores e nesta rodada, "titulos dos aplicativos"
virou uma busca por captura de tela ou abas; "teletransporte" virou um suposto
controle de UI. A busca lexical confirma palavras dessa reformulacao, nao a
adequacao ao pedido original. Nao e simplesmente ausencia do schema correto.

O caso `dev_titles/current/0` tornou a falha precisa: apos a busca, o modelo
propos **listar_janelas_windows E capturar_tela_windows no mesmo lote**. O schema
correto estava presente e foi usado na proposta. Como a captura nao pertencia
ao escopo sintetico autorizado, o Harness recusou **todo o lote antes de agir**.
Na regressao final isso voltou a ocorrer. A protecao esta correta; a selecao
incluiu trabalho nao pedido. Nao significa que toda execucao normal de Auren
falharia com o mesmo erro: o experimento aplica um escopo minimo explicito.

### A busca lexical e o planejamento errado reforcavam um ao outro

O ranking pesa nome, descricao e prefixos. Ele nao separa "uma funcao implementada"
de "um controle imaginado numa interface". Resultados por "capturar" e "interface"
podem ser lexicalmente corretos e semanticamente inadequados. A validacao de
call_id e o recalculo de metadados impedem adulteracao de schemas, mas nao provam
que a consulta ou o proximo passo servem ao objetivo. Nao foram relaxados.

### O contexto tem ruido, mas nao se demonstrou que remove-lo resolva

O prompt compartilhado tem 12728 caracteres; o estado inicial do caso de titulos
tem 1121, incluindo lembretes visuais mesmo sem necessidade de visao. Isso e uma
hipotese plausivel de priming. Entretanto, a ablação de selecao com objetivo puro,
sem o texto de estado, continuou produzindo busca, enquanto expor a leitura
direta eliminou essa rodada. A amostra nao permite atribuir causalidade exclusiva
ao contexto. Nao se removeram instrucoes ou verificacoes de seguranca do runtime.

### Ferramentas auxiliares tambem viravam tarefas adicionais

Uma consulta de audio propôs `obter_audio_windows` junto com `obter_status_windows`.
O Router herdava COMMON_TOOLS em dominios ja identificados. A politica anterior
e v1 continham essas opcoes; o refinamento v2 adia as ancoras sem relacao com o
dominio. Isso diminui oportunidades para passos extras, mas nao e prova de que
um schema menor sempre melhora a precisao: o modelo varia entre repeticoes.

### Schemas iniciais menores nao significam tarefas mais baratas

Uma busca custa uma rodada, sua saida, a chamada seguinte e o prompt compartilhado
novamente. Sem previous_response_id, cada chamada e autocontida. Cache ajuda,
mas toolsets que mudam apos uma busca podem gerar novas escritas de cache.
A continuidade conserva apenas a rodada anterior e estado compacto; ferramentas
fora do conjunto atual podem precisar de outra busca.

Exemplo medido: para titulos, a base usou 6629 tokens de entrada em uma chamada;
a #173 usou aproximadamente 7170 em duas, podendo falhar pelo lote extra. O
bootstrap usou 3527 em uma. Ja para clipboard, manter cinco consultas disponiveis
acrescenta contexto quando a ferramenta certa continua adiada: ha tres chamadas
em varios ensaios, contra duas — ou uma tentativa incorreta — na base.

## 3. Alternativas consideradas antes de implementar

| Alternativa | Evidencia/decisao |
| --- | --- |
| Catalogo completo, sem etapa de busca | Controle de selecao: acerta titulos, mas tambem propoe screenshot para capacidade ausente. Grande superficie inicial; nao resolve tudo. |
| Busca atual com objetivo puro | Ablação sem execucao: ainda busca; nao justifica alterar o estado de seguranca. |
| Bootstrap de consultas existentes | Escolhe diretamente a leitura correta nos probes de titulos; 2504 caracteres contra 24185 do catalogo completo. Implementado opt-in. |
| Bootstrap mais indice de nomes/descricoes | 6545 caracteres no probe; mesma selecao em titulos e ainda uma busca imaginada no pedido impossivel. Sem beneficio demonstrado para o custo extra. |
| Prefetch lexical do pedido original | Nos probes escolhidos nao acrescentou capacidade ao bootstrap; nao promovido como ganho. |
| Seletor hierarquico com chamada extra/embeddings | Nao implementado: adicionaria dependencia ou rodada; sem evidencia local que justifique esse custo para 49 funcoes. Nao se afirma que seja inviavel em outro catalogo. |
| Tool search nativo hospedado | Documentado, mas nao exercitado: exige outro protocolo de itens/continuidade e verificacao de custos de ferramentas. Nao se assumiu equivalencia com o contrato/ledger local. |

**Como outros sistemas tratam isso, fontes primarias consultadas:**

- [OpenAI Tool Search](https://developers.openai.com/api/docs/guides/tools-tool-search)
  preserva nomes/descricoes pesquisaveis e carrega definicoes sob demanda; a
  documentacao trata tambem de continuidade/cache. O nosso "so busca" nao
  reproduz automaticamente essa superficie informativa.
- [Anthropic Advanced Tool Use](https://www.anthropic.com/engineering/advanced-tool-use)
  combina ferramentas frequentes disponiveis e outras adiadas, e explicita o
  custo da etapa de busca. Os ganhos publicados deles nao foram transferidos
  para Auren como se fossem resultados deste experimento.
- [LangChain LLM Tool Selector](https://docs.langchain.com/oss/python/langchain/middleware/built-in#llm-tool-selector)
  oferece selecao por uma chamada de LLM anterior ao modelo principal; e uma
  alternativa de arquitetura, nao uma otimizacao gratuita.
- [Home Assistant Conversation](https://www.home-assistant.io/integrations/conversation/)
  usa frases/intents e slots para comandos conhecidos. O Auren ja possui Router,
  LocalDecisionEngine e fast paths; nao se copiou uma gramatica nova para os casos
  desta amostra nem se transformou frase ambigua em execucao local.

## 4. Mudanca experimental escolhida

A alteracao de runtime desta rodada fica em **core/router.py**. Reutiliza
COMMON_TOOLS, os grupos e a busca existente. Sem dominio claro, a politica nova
expoe as consultas comuns de memoria, status e janelas, mais abas e audio,
junto da busca. Com dominio conhecido, v2 conserva a uniao dos grupos realmente
detectados e adia ancoras de outros dominios. Resultados validos de busca e a
ferramenta anterior continuam disponiveis pela mecanica existente.

Nao ha regex nova para frases de teste, lista de alvos especiais, alteracao dos
schemas/handlers de ferramentas, segundo executor, modelo adicional ou mudanca
de contexto/permissao. Uma ferramenta nao disponivel inicialmente continua
descobrivel: o teste de registry dinamico carrega uma funcao sintetica nova,
mantem dominios compostos e comprova ausencia de vazamento entre tarefas. O Live
de clipboard tambem executou a sequencia busca -> leitura pelo Dispatcher.

**Ativacao somente em processo isolado de experimento:**
`AUREN_DYNAMIC_TOOL_DISCOVERY=1` e `AUREN_DISCOVERY_POLICY=bootstrap` antes de iniciar.
Nao foi ativado na instalacao pessoal. Sem a segunda variavel, a #173 anterior
continua igual; com a primeira desligada, o comportamento legado permanece.
Nao e a politica padrao nem recomendacao de rollout.

## 5. Desenho da avaliacao e limites de medicao

- Dez probes pagos de selecao **sem executar ferramentas** precederam a mudanca.
  [Resultados individuais](pr173-round2/selection-probes.json).
- Painel v1: 8 prompts, duas repeticoes por versao = 48 ensaios, sendo 6 prompts
  reservados ate a politica estar congelada em `924e970`.
- Refinamento v2: 3 prompts novos, duas repeticoes por versao = 18 ensaios; dados
  e politica congelados em `87b4740`. Depois, painel explicito de regressao com
  4 prompts conhecidos, uma repeticao por versao = 12 ensaios.
- Total: **78 ensaios de tarefa**, nao 78 prompts independentes; 11 prompts unicos
  no conjunto de tarefas. Os probes reutilizam alguns objetivos conhecidos.
- Sucesso requer estado completed, todas as operacoes/observacoes necessarias,
  fatos sinteticos corretos, alvo/aba correta e nenhuma proposta fora do escopo.
  Resposta verbal ou sucesso de mock isolado nao bastam.
- O avaliador bruto era estrito demais em acentos e nome exato da ferramenta:
  "Relatorio"/"Relatório" e leitura de pagina por `obter_contexto_navegador`
  recebiam falsos negativos. A auditoria usa normalizacao ja existente no Auren
  e equivalencia comprovada pela fixture, igualmente nas versoes. Preserva
  `raw_success`, `audited_success`, evidencias positivas registradas antes da
  redacao de privacidade e os logs privados. Nao desmascara clipboard nem aceita
  tarefa failed como sucesso. Audio exige tambem o estado de mudo correto.
- Medianas sao tempo do Harness, incluindo API e revisores; nao incluem abrir
  os subprocessos. Probes tem outra medicao e nao foram misturados nessas medias.
- Mesma chave de cache e ordem rotacionada nao garantem caches equivalentes:
  categorias efetivamente reportadas foram contabilizadas. Cache neutro e uma
  **estimativa secundaria**, nao custo pago, nem substituto para medir chamadas.
- Amostra pequena, sintetica e com duas repeticoes: nao comprova taxa geral de
  acerto, significancia estatistica, uso diario ou conclusao de tarefas reais.
  O runtime final nao foi reexecutado em todo o painel v1; nao misturar os SHAs.

## 6. Resultados comparativos

### Painel inicial: 16 ensaios por versao, incluindo os reservados

| Medida | Base #172 | #173 atual | Bootstrap v1 |
| --- | ---: | ---: | ---: |
| Sucessos auditados | 10/16 | 11/16 | 13/16 |
| Selecao sem proposta extra fora de escopo | 13/16 | 13/16 | 15/16 |
| Chamadas API totais | 31 | 43 | 37 |
| Tokens entrada / saida | 157229 /754 | 163089 /1364 | 142008 /994 |
| Custo estimado por uso, US$ | 0,00757989 | 0,01488937 | 0,00989753 |
| Mediana por ensaio, s | 4,251 | 5,068 | 4,048 |

Nos 12 ensaios reservados por versao, os sucessos foram 8/12, 8/12 e 9/12.
O bootstrap diminuiu entrada e falhas em alguns casos; **aumentou chamadas e custo
efetivo contra a base**. Nao atende o criterio de menor custo total.

### Runtime final: 6 ensaios novos e 4 de regressao por versao

Nos tres prompts novos, **6/6 passaram em cada versao**, com 8 chamadas cada.
O custo foi US$ 0,00196108 (base), US$ 0,00202660 (atual), US$ 0,00362160
(nova). A nova teve mais escritas de cache ao estrear os novos toolsets.

Somando somente os paineis realmente executados com v2:

| Medida | Base #172 | #173 atual | Bootstrap v2 |
| --- | ---: | ---: | ---: |
| Sucessos auditados | 8/10 | 9/10 | 10/10 |
| Chamadas totais | 15 | 20 | 20 |
| Tokens entrada / saida | 63700 /379 | 76424 /597 | 75575 /556 |
| Tokens cached / cache write | 59019 /4636 | 66581 /9783 | 57405 /18110 |
| Custo estimado por uso, US$ | 0,00280318 | 0,00450577 | 0,00635480 |
| Mediana por ensaio, s | 3,512 | 3,845 | 3,589 |

A base e mais barata em parte porque falhou cedo em duas tarefas. Mesmo
restringindo aos **sete ensaios bem-sucedidos nas tres versoes**, a proposta nao
vence: 10 chamadas em cada, entrada 38153 /39833 /38699 e custo
US$ 0,00214698 /0,00221922 /0,00388527. A estimativa sem cache tambem nao supera
a base nesse subconjunto: US$ 0,00986705 /0,01028705 /0,01001075.

Exemplos que impedem uma conclusao seletiva:

- Titulos: a nova passa com uma chamada; a atual volta a propor captura extra.
- Clipboard: descoberta e execucao funcionam, mas custam tres chamadas; nao
  confundir cobertura preservada com economia.
- Continuacao para segunda aba: a nova passou no painel final, mas usou **seis
  chamadas e 13,116 s**, contra cinco e 8,835 s na atual. A base retornou completed
  sem cumprir os fatos/observacao esperados: foi marcada falha pelo oracle.
- "Leia a pagina e localize o arquivo": nas tres versoes ocorre
  `task_evidence_missing`. A heuristica compartilhada associa "leia" ao arquivo
  mencionado, embora o pedido de leitura seja da pagina. Nao foi alterada a
  verificacao para fazer o experimento passar. Precisa de revisao de requisitos
  por etapa; a descoberta nao resolve esse problema.
- No ensaio offline roteirizado de leituras compostas, uma leitura terminal pode
  tentar finalizar antes da outra e encontrar evidencia faltante. Os roteiros
  offline nao foram apresentados como sucesso real de continuidade.

### Matriz offline de 100 prompts

Mesmo metodo anterior: disponibilidade no schema ou no plano local, uma busca
oracle quando necessaria, tokens estimados por ceil(chars/4), 11 tempos locais
por prompt. Isso mede superficie/roteamento, nao sucesso ou fatura de API.

| Medida | Base | Atual | Bootstrap v1 | Bootstrap v2 |
| --- | ---: | ---: | ---: | ---: |
| Caracteres schemas iniciais | 1465159 | 319144 | 398908 | 360374 |
| Tokens estimados schemas | 366348 | 79806 | 99747 | 90118 |
| Disponibilidade inicial, 40 rotulados | 39 | 39 | 39 | 38 |
| Apos ate uma busca simulada | 39 | 40 | 40 | 40 |
| Buscas simuladas | 0 | 1 | 1 | 2 |

O refinamento tem um custo: um pedido composto cujo segundo dominio nao e
reconhecido pode precisar de busca para recuperar a ancora removida. Nao existe
garantia geral de continuidade por essa matriz. Nenhum novo efeito local indevido
foi observado nos 100 prompts, mas isso nao e taxa de acerto do modelo.

## 7. Orcamento encerrado e tokens reais

[Ledger auditavel](pr173-round2/paid-ledger.json),
[resumo consolidado](pr173-round2/summary.json).

- **176 chamadas**: 10 probes, 159 principais, 7 revisoes de intencao.
- Entrada **720598**, saida **4920**, cached **584366**, cache write **134990**,
  raciocinio reportado **0** (raciocinio seria parte do teto de saida).
- Estimativa reconciliada por usage: **US$ 0,05158722**; fatura nao confirmada.
- Exposicao conservadora reconciliada: **US$ 0,4471188**.
- Maior exposicao incluindo a reserva pendente antes de uma chamada:
  **US$ 0,464436**, abaixo da linha interna US$ 0,49 e do teto US$ 0,50.
- Nenhum erro de transporte/usage desconhecido. Ledger `closed=true` impede
  continuacao acidental; nao ha novas chamadas autorizadas por este run.

Tarifas verificadas antes de gastar na [documentacao oficial de GPT-5.6
Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna): input US$ 0,20/M,
cached US$ 0,02/M, writes 1,25x input = US$ 0,25/M, output US$ 1,20/M.
As categorias foram reconciliadas pelos tokens efetivamente reportados.

Cada chamada reservou antes da rede o limite UTF-8 do payload +8192 tokens de
framing, a US$ 0,60/M input e US$ 3/M output. So usage valido, modelo correto e
bounds satisfeitos liberam a parte nao usada da reserva; a exposicao reconciliada
continua usando essas tarifas conservadoras, sem descontos de cache. Falha ou
uso desconhecido conserva reserva e bloqueia chamadas seguintes. Nao se somam
reservas ja reconciliadas como se fossem gasto; o ledger conserva cada reserva
original e cada liquidacao para auditar a sequencia. Sem imagens/audio, endpoints
customizados ou ferramentas hospedadas com cobranca adicional.

## 8. Reproducao, artefatos e testes

Arquivos de avaliacao:
[runner](../../scripts/diagnosticos/discovery_round2_run.py),
[casos iniciais](../../scripts/diagnosticos/discovery_round2_cases.json),
[validacao nova](../../scripts/diagnosticos/discovery_round2_validation.json),
[regressoes](pr173-round2/regression-cases.json),
[probes](../../scripts/diagnosticos/discovery_round2_probe.py),
[auditoria offline](../../scripts/diagnosticos/discovery_round2_score.py).

Resultados individuais sem respostas livres/logs privados:
[48 ensaios v1](pr173-round2/stage1-results.jsonl),
[18 ensaios novos v2](pr173-round2/fresh_validation-results.jsonl),
[12 ensaios de regressao](pr173-round2/regression_panel-results.jsonl),
[400 linhas da matriz](pr173-round2/offline-matrix.jsonl),
[diagnostico inicial](pr173-round2/offline-diagnosis.json).
Cada ensaio identifica SHA, chamadas do ledger, propostas por rodada, resultados,
tokens, custos e duracao. O resumo separa cohorts; nao atribui resultados v1 a v2.

Comandos principais, a partir do checkout isolado:

```text
py -3.13 scripts/diagnosticos/offline_python.py -m pytest -q
py -3.13 scripts/diagnosticos/offline_python.py -m pytest -q tests/test_discovery_bootstrap.py tests/test_discovery_round2_budget.py tests/test_discovery_round2_scoring.py
py -3.13 scripts/diagnosticos/offline_python.py scripts/diagnosticos/discovery_round2_run.py --offline --evidence <nova-pasta-fixtures>
py -3.13 scripts/diagnosticos/discovery_round2_score.py --evidence <resultados-locais> --output <auditoria.json>
```

O runner pago requer `--run`, checkouts `--base`/`--current`, casos e ledger
explicitos. Os manifests privados registram hash dos casos e ordem. Para v2,
usou-se `--cases-file discovery_round2_validation.json --split heldout --repeats 2`
com **o mesmo** `--budget` da rodada. Os ledgers publicados estao fechados;
reproduzir comandos offline nao exige nova autorizacao, repetir API paga sim.

Validacao: 82 testes existentes antes de mudar runtime; 13 testes iniciais de
reserva; testes dedicados de bootstrap/registry dinamico/escopo/permissoes,
orcamento e oracle; suites completas intermediarias 1312 e 1315 aprovadas,
8 skips em cada. Suite local final **1316 passed /8 skipped**, 96,16 s, codigo
`09dc184` (runtime `87b4740`). Skips de symlink WinError 1314, nao aprovados.
Credenciais removidas e sockets Python externos bloqueados nos testes offline.

Tentativas registradas: o primeiro fake de budget excedia seu proprio bound e
foi corrigido; o primeiro callback offline tinha assinatura incompativel com o
Harness, identificado antes do painel de API e corrigido. Esses resultados
nao foram contados como sucesso funcional. O oracle foi corrigido por motivos
descritos acima, sem alterar modelos, permissoes ou prompts reservados.

[CI intermediario 924e970](https://github.com/Yamatosemj/aurenOFC/actions/runs/39367100717):
Linux 1275 passed/45 skipped, Windows hospedado 1319 passed/1 skipped.
O CI do HEAD de entrega e registrado na descricao da PR, sem commit apenas para
copiar numeros de run. Nenhum workflow, secret, autorizacao ou runner pessoal
foi modificado/acionado.

## 9. Parecer tecnico

O bootstrap e uma melhoria util contra a busca cega em consultas frequentes.
Ainda assim, **nao compensa como substituicao geral demonstrada da #172**: os
ganhos sao dependentes do pedido, ha mais chamadas em descoberta/continuacao,
mais escritas de cache e nenhum ganho de custo na comparacao das mesmas tarefas
bem-sucedidas. A taxa 10/10 do painel final e promissora, mas pequena e sintetica.

Recomendo manter a implementacao anterior de referencia (#172, descoberta off),
conservar os experimentos opt-in desta PR e nao promover uma nova politica
padrao. Os proximos problemas tecnicos sao extrair requisitos por etapa sem
confundir fontes e medir politicas de continuidade/cache por tarefa; nao
adicionar mais aliases ou um modelo extra sem demonstracao de ganho. Essas
pendencias nao sao permissao para agir no Windows, instalar, gastar novamente
ou fazer merge.
