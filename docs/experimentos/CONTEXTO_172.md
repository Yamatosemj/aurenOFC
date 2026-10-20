# Auditoria de contexto sobre a #172 — experimento offline

A economia demonstrada nesta etapa e pequena: **268 tokens de entrada proxy, 0,278%**, sem chamadas adicionais nas mesmas tarefas roteirizadas. Nao ha economia faturada comprovada. A candidata mantem a #172 como referencia e duas compactacoes de JSON opcionais; nao incorpora a descoberta da #173.

Base: `48717bb68fd3545d31aa33028261fa33f9f50177`, HEAD da #172 conferido no GitHub. Runtime experimental: `b3c9a2bda3ccee7c7ea19b194097193f67283b4f`; captura final da matriz: `e62f316`. Branch separada `experiment/context-audit-172`. #173 preservada em draft no `76283bf`; main remota conferida em `70b040d`. Sem merge ou alteracao da instalacao pessoal. **Zero chamadas pagas nesta etapa.**

## 1. O que efetivamente segue para a API

O caminho principal permanece Harness -> Orchestrator -> Router existente -> OpenAIProvider. A captura ocorre em `responses.create`, substituido permanentemente por transporte falso no diagnostico. Nao e apenas uma contagem dos schemas iniciais.

| Componente | Envio observado na #172 | Necessidade, redundancia e oportunidade |
| --- | --- | --- |
| Instrucoes globais | Campo `instructions`, 12.728 caracteres / **2.909 tokens proxy**, em toda chamada principal | Identidade, ASR, selecao de ferramentas, restricoes, privacidade, verificacao e conclusao. Regras de dominios diversos aparecem mesmo em tarefas de audio. Candidato a auditoria de clausulas, sem remover garantias globalmente necessarias. |
| Schemas | `tools`, selecionados pelo Router a cada rodada | Registry completo: 49 ferramentas, 22.883 caracteres / 5.157 tokens proxy em JSON canonico. A lista completa nao e enviada sempre. Preservar nomes, argumentos, restricoes e descricoes; minificar o JSON HTTP nao prova economia no contexto renderizado pelo servidor. |
| Objetivo | Texto integral no inicio do estado | Indispensavel para manter alvo, condicoes e ordem. Nao substituir o pedido pelo plano heuristico. |
| Plano local | Etapas numeradas com instrucao, quando TaskManager e persistente | Repete partes do objetivo, mas conserva referencias operacionais e nao constitui autorizacao. Apenas espacos JSON foram compactados opcionalmente. |
| Regras locais do Harness | Evidencia da tarefa atual, nao repetir efeitos, dependencia entre chamadas, coordenadas e verificacoes pendentes | Ha sobreposicao com o prompt global. Os marcadores dinamicos informam uma pendencia concreta. Nao excluir como se fossem texto decorativo. |
| Contexto recuperado | Construido uma vez por mensagem, incluido no estado inicial **e nas continuacoes normais** | Turnos, tarefas, fatos, memoria, estrategias e skills podem compartilhar informacao. Deduplicar requer preservar a origem e o fato de que contexto antigo nao comprova estado atual. |
| Historico de ferramentas | Ate 2 itens anteriores no estado, com nome, argumentos redigidos e resultado limitado | Nao e toda a cadeia da tarefa. O helper exclui por contagem as entradas da rodada que ja recebe como outputs. Remover mais pode perder dependencias e verificacoes. |
| Resposta anterior do modelo | Somente `reasoning` e `function_call` da resposta imediatamente anterior, em ordem | Manter objetos, argumentos, IDs e associacao com outputs. Mensagens finais antigas nao sao reenviadas por esse mecanismo. |
| Resultados de ferramentas | `function_call_output`; representacao limitada pelo Harness, normalmente ate 2.200 caracteres | ToolResult ja usa JSON compacto quando estruturado. Resultados de arquivo podem ter continuacao; cortes devem manter semantica de pagina/truncamento. Nao resumir evidencia livremente. |
| Visao | Mensagem user com imagem e geometria associada, quando houver resultado visual | Fora da matriz textual. Nao equivale a caracteres ou tokens de texto. Snapshot e coordenadas devem continuar coerentes. |
| Revisor de intencao | Chamada separada, sem tools; 4.336 caracteres / 1.016 tokens proxy de instrucoes | Pedido original ate 4.000 caracteres, ate 12 propostas, argumentos ate 3.000 cada; 2 resultados anteriores de ate 2.200, e esclarecimento confirmado quando existir. JSON de resposta estrito, limite de 300 tokens de saida. Nao e chamado para toda leitura ou proposta simples exata. |
| Revisor de conclusao | Chamada separada quando exigida pelo Harness persistente; 2.789 caracteres / 597 tokens proxy de instrucoes | Recebe objetivo, resposta candidata, plano e **todos os passos** com argumentos/sucesso/resultados. JSON estrito, ate 1.200 tokens de saida. A verificacao local das referencias e leituras posteriores continua obrigatoria. |
| Recuperacoes | Estado adicional em respostas vazias, veto/replanejamento, verificacoes pendentes ou conclusao incompleta | Podem adicionar rodadas e contexto. Nao confundir o limite de uma chamada com custo da tarefa inteira. Veto nao permite repetir a proposta proibida. |

Fontes concretas: [provider](../../providers/openai_provider.py), [Harness](../../core/harness.py), [montagem da rodada](../../core/harness_round_input.py), [estado](../../core/harness_state.py), [tools](../../core/harness_tools.py), [intencao](../../core/intent_verification.py), [conclusao](../../core/task_verification.py), [sessao](../../core/session.py), [skills](../../skills/loader.py) e [uso/custo](../../core/usage.py).

O Harness passa `response_id=None` e effort `none`. O provider aceita previous_response_id para outros chamadores, mas isso nao e continuidade ativa no ciclo auditado. A chamada principal configura `parallel_tool_calls=True`, cache key `auren-v47` e TTL `30m`; o Harness/Dispatcher executa a sequencia em ordem, mantendo permissoes por chamada. Os revisores enviam `tools=[]`, `store=False`, formato de resposta proprio e nao configuram explicitamente chave/TTL de cache. Isso nao permite inferir cache zero.

### Contexto conversacional e limites

SessionContextManager usa esta ordem: 6 turnos recentes (300 caracteres por user, 700 por assistant); ate 3 tarefas anteriores do mesmo chat, com 2 resultados de ate 800 caracteres apenas na mais recente; ate 3 fatos; ate 3 conversas relevantes, excluindo turnos ja presentes; ate 3 estrategias; ate 3 skills relevantes. O total renderizado tem orcamento de 3.600 caracteres. Skills possuem limite proprio de 2.200 e corpo de ate 700 por skill. O estado completo do Harness aplica outro corte, de 4.500 caracteres, seguido do marcador de truncamento quando necessario.

O contexto e montado **antes** de registrar o pedido atual como turno: ele ja evita duplicar automaticamente esse pedido. A memoria lexical ja exclui conteudos identicos aos turnos recentes. Resultados atuais ja sao separados do historico textual. Portanto essas tres economias nao sao novas propostas.

No teste de continuidade de abas, o segundo pedido recebe **936 caracteres** recuperados: 264 de turnos, 284 de tarefa anterior, 384 de estrategia e separadores. Esse contexto reaparece em suas tres chamadas principais. As tres secoes descrevem parcialmente a mesma atividade. E uma oportunidade real, mas substituir todas por uma frase pode perder titulos, URLs, ordem e proveniencia.

**Divergencia documental corrigida nesta branch:** a arquitetura 03 dizia que as continuacoes nao traziam o contexto completo; `harness_round_input` usa `incluir_contexto=True` na #172. A captura confirma o reenvio. A arquitetura 01 tambem foi corrigida nesse ponto.

**Limite preexistente reproduzido:** com contexto sintetico de 3.600 caracteres, o corte final do estado elimina os lembretes locais de verificacao visual/navegador que ficam depois dele. O prompt global continua integral e as guardas executaveis permanecem; o diagnostico nao demonstra um bypass. O mesmo ocorre na referencia e na candidata. Nao reduzir esse teto para alegar economia. Uma reorganizacao futura precisa reservar espaco para avisos obrigatorios e medir o impacto da eventual perda de contexto auxiliar. [Inventarios individuais](contexto172-evidence/inventory-base.json) e [candidata](contexto172-evidence/inventory-combined.json).

## 2. Mudancas implementadas, isoladas e reversiveis

| Variante | Flag, somente valor `1` | Alteracao |
| --- | --- | --- |
| Revisores | `AUREN_CONTEXT_COMPACT_REVIEWS` | Remove apenas espacos de separacao do JSON textual dos dois revisores. Preserva chaves, valores, ordem, strings internas, resultados, propostas e confirmacoes. |
| Plano | `AUREN_CONTEXT_COMPACT_PLAN` | Mesma compactacao, apenas no JSON do plano dentro do estado. Mantem objetivo e todas as etapas. |
| Combinada | Ambas | Soma das duas mudancas. |

Sem flags, o texto serializado conserva o formato da #172. Nenhuma flag pessoal foi ativada. O helper [context_encoding](../../core/context_encoding.py) nao seleciona contexto ou ferramentas. Nao houve mudanca no Router, schemas, Dispatcher, PermissionManager, prompts de seguranca, contratos, formatos de resposta, limites, modelos ou executores.

**Alternativas examinadas e nao adotadas nesta etapa:**

- Remover linhas vazias do prompt: 12.728 -> 12.709 caracteres, **2.909 -> 2.909 tokens proxy**. Zero beneficio; mudanca descartada.
- Compactar ToolResult: ja implementado na referencia. Nao atribuir esse ganho ao experimento.
- Cortar historico/contexto ou resultados: exigiria provar preservacao de alvos, referencias e evidencia. Limites por caracteres ja podem truncar; nenhuma reducao adicional feita.
- Deduplicar turnos/tarefas/estrategias: promissor, mas precisa de representacao que preserve origem e dados de continuidade. Nao retirar uma fonte somente porque cita o mesmo assunto.
- Eliminar revisores ou trocar por outro seletor: nao implementado; seria alteracao das verificacoes ou mais uma chamada ao modelo.
- Congelar um toolset diferente ou reformar o roteador: fora destas otimizacoes; a comparacao verifica os mesmos hashes de schemas por rodada.

## 3. Metodo e equivalencia

[Runner](../../scripts/diagnosticos/context_audit.py) exclusivamente offline, sem opcao Live; respostas do modelo roteirizadas, handlers sinteticos para todas as entradas do Dispatcher. Router, Harness, contratos, PermissionManager, serializadores do provider, TaskManager persistente e verificacoes de conclusao sao reais. Os pareceres semanticos sao simulados e continuam passando pelos parsers/validadores reais. Nao se mede inteligencia ou confiabilidade estatistica do modelo.

Foram usados **8 cenarios / 9 mensagens-tarefas por variante**: consultas de audio/janelas/pagina, duas acoes em lote com leitura final, sequencia de leitura-mutacao-verificacao, continuidade de duas mensagens em abas e recusa de capacidade inexistente. Quatro cenarios sao novos controles reservados; nao houve ajuste de politica para suas palavras. Os prompts estao [versionados](../../scripts/diagnosticos/context_audit_cases.json), com hash no manifesto. O termo heldout indica separacao do painel, nao validacao cega de modelo real.

Cada cenario/variante roda em processo separado. Ordem em rotacao ciclica balanceada; mesmo mundo inicial, banco temporario e persistencia pos-tarefa finalizada antes da mensagem seguinte. Atalhos de execucao sao desabilitados igualmente no fixture para inspecionar o caminho com modelo. Encerramentos locais do proprio Harness permanecem ativos: uma listagem pode finalizar apos uma unica chamada principal. Esses fixtures nao representam a distribuicao inteira do uso diario.

O [agregador](../../scripts/diagnosticos/context_audit_summary.py) exige igualdade de chamadas por fase, acoes/argumentos/resultados, estado final, fatos e contexto recuperado. Confere hashes de instrucoes e schemas em cada rodada. O teste de continuidade conserva os mesmos titulos/URLs/codigo da segunda aba. Strings de teste incluem acentos, aspas, espacos internos e instrucoes hostis tratadas como dados. Os limites e marcadores de confirmacao continuam testados.

**Tokens:** tiktoken 0.12.0, encoding `o200k_base`, instalado em diretorio auxiliar isolado, sem instalar dependencia global. Contagem por componente textual, com schemas/objetos em JSON canonico; soma nao inclui a renderizacao oculta, overhead exato de papeis ou tokenizador especifico do modelo. Saidas tambem sao proxies de respostas roteirizadas. Nao sao `usage` da API. Bytes HTTP menores nao foram contabilizados como economia automaticamente.

As chamadas pagas, cache reads/writes e latencia da API sao **nao medidos** (`null` nos registros), e o gasto efetivo desta etapa e **US$ 0**. Nao preencher essas metricas com zeros que aparentem uma medicao Live.

## 4. Resultados individuais e totais

| Cenario | Chamadas simuladas por variante | Entrada #172 | So revisores | So plano | Combinada | Economia combinada |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Audio atual | 2 | 7.642 | 7.642 | 7.636 | 7.636 | 6 |
| Janelas | 1 | 4.130 | 4.130 | 4.127 | 4.127 | 3 |
| Audio em lote | 5 | 13.826 | 13.785 | 13.805 | 13.764 | 62 |
| Audio sequencial | 6 | 17.759 | 17.714 | 17.715 | 17.670 | 89 |
| Abas + segunda mensagem | 6 | 21.583 | 21.558 | 21.571 | 21.546 | 37 |
| Audio novo | 5 | 13.830 | 13.789 | 13.809 | 13.768 | 62 |
| Pagina atual | 2 | 9.365 | 9.365 | 9.359 | 9.359 | 6 |
| Capacidade inexistente | 1 | 8.399 | 8.399 | 8.396 | 8.396 | 3 |
| **Total** | **28** | **96.534** | **96.382** | **96.418** | **96.266** | **268** |

Todas as colunas de tokens sao proxies offline. Cada variante teve 20 chamadas principais, 4 revisoes de intencao e 4 de conclusao: **28, sem reducao**. Saida proxy: **908** em cada uma. Total entrada+saida: 97.442 -> 97.174 (**0,275%**). Entrada media por mensagem-tarefa concluida no fixture: 10.726 -> 10.696,22. Os 8 cenarios/9 tarefas concluem com as mesmas acoes e fatos nas quatro variantes; isso e reproducao controlada, nao taxa de sucesso Live.

| Origem da entrada na #172 | Tokens proxy | Participacao |
| --- | ---: | ---: |
| Instrucoes dos tres tipos de chamada | 64.632 | 66,95% |
| Schemas de ferramentas | 20.681 | 21,42% |
| Estados/revisoes como string e mensagens | 9.533 | 9,88% |
| Schema de resposta dos revisores | 868 | 0,90% |
| Chamadas e outputs de ferramentas | 820 | 0,85% |

Esse peso depende do painel: ferramentas retornam textos curtos aqui. Arquivos extensos, DOM e imagens podem alterar bastante a distribuicao. Nao extrapolar 66,95% a todo uso do Auren.

Medianas de duracao **local do fixture**, incluindo SQLite/guards e tokenizacao: #172 225,031 ms; revisores 202,633 ms; plano 203,664 ms; combinada 221,305 ms. Uma observacao por cenario, sem inferencia estatistica. A combinada foi mais lenta em alguns casos (abas: 355,434 -> 360,714 ms; audio novo: 274,770 -> 284,885 ms). **Nao ha ganho de latencia da API demonstrado.** Registros por chamada/cenario em [evidencias](contexto172-evidence/summary.json) e [comparacao auditada](contexto172-evidence/comparison.json).

### Custo: projecao, nunca fatura

Tarifas de referencia consultadas em 20/10/2026 para [gpt-5.6-luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna): por milhao, input US$ 0,20; cached US$ 0,02; output US$ 1,20; write 1,25x input, US$ 0,25. Aplicadas aos **proxies** somente para sensibilidade:

| Hipotese artificial sobre toda a entrada | #172 | Combinada | Diferenca |
| --- | ---: | ---: | ---: |
| Tudo sem cache | US$ 0,02039640 | US$ 0,02034280 | US$ 0,00005360 |
| Tudo como nova escrita | US$ 0,02522310 | US$ 0,02515610 | US$ 0,00006700 |
| Tudo como leitura de cache | US$ 0,00302028 | US$ 0,00301492 | US$ 0,00000536 |

Sao cenarios aritmeticos, nao limites garantidos: misturas reais de hits/escritas, overhead, saidas diferentes ou rodadas adicionais podem alterar a comparacao. Mesmo uma pequena perda de cache pode superar esse ganho de formatacao.

## 5. Cache e continuidade

A [documentacao oficial de prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching) descreve reutilizacao por prefixos e tarifas distintas para tokens uncached, cached e escritos; a escrita nao e taxa adicional sobre o mesmo token. Prefixos, elegibilidade e disponibilidade precisam ser observados em `usage`. Nesta etapa nao foram inferidos hits a partir de igualdade textual. A chave/TTL existentes foram preservados; tambem nao se adicionou prewarm pago.

Cache explicito em conteudo estavel e uma hipotese posterior interessante para separar instrucoes reutilizadas de estado volatil. Nao foi ativado: exige conferir suporte do SDK e representacao no provider, e comparar writes/hits reais em condicoes frias e quentes. Mudar o prefixo para compacta-lo pode provocar uma escrita inicial nova.

O cache local de **resposta** e distinto: o Orchestrator so considera strings curtas, sem tool_choice e sem sinais de estado/acao. O estado normal do Harness e maior; nao se pode creditar ao cache de respostas uma economia que ele nao produziu nestes fixtures.

`previous_response_id` pode simplificar transporte/continuidade, mas nao transforma historico em entrada gratuita: a [documentacao de estado de conversa](https://developers.openai.com/api/docs/guides/conversation-state) informa que os tokens anteriores da cadeia continuam faturados como entrada. A referencia ja reenvia somente a rodada anterior e evidencia limitada. Trocar isso por uma cadeia crescente exige medir tokens acumulados, privacidade e continuidade; nao foi adotado como atalho de economia.

## 6. Regressao, testes e limites

Local, Python 3.13.15, Windows; suite com credenciais removidas e sockets Python externos bloqueados pelo `offline_python.py` (loopback de fixtures permitido; nao e sandbox de SO):

- Referencia #172 `48717bb`: **1.265 passed / 8 skipped**, 97,53 s.
- Candidata, runtime de `b3c9a2b`, **ambas as flags ligadas**: **1.272 passed / 8 skipped**, 98,00 s.
- Sete casos novos de testes de serializacao/protecao; 43 testes focados aprovados incluindo sessao, continuidade reasoning e revisao composta.
- Os 8 skips locais sao de symlinks sem privilegio Windows; nao foram tratados como aprovados.
- Veto semantico sintetico, referencia/candidata: nenhuma mutacao executada; leitura de audio subsequente permitida, tarefa falha com `intent_replan_empty`.
- Permissao negada sintetica, referencia/candidata: nenhuma mutacao bem-sucedida, interrupcao com `permission_denied`.

Resultados funcionais roteirizados: nenhuma regressao observada neste painel. A auditoria conserva `answer_matches` literal alem de `facts_ok`: respostas locais do Harness para listagens nao precisam copiar a frase roteirizada para preservar os mesmos titulos/URLs. O criterio requer acoes esperadas, fatos e conclusao; nao transforma falha de tarefa em sucesso.

**Pendente:** selecao e resposta do modelo real, tokens reais de entrada/saida/cache/write, custo faturado, latencia da API, fixtures de arquivos longos/visao, tarefas abertas e uso prolongado. Nem os testes nem a igualdade de objetos JSON garantem que o modelo tera comportamento identico. Nenhum teste pago foi tentado.

## 7. Decisao tecnica e proxima prioridade

Manter estas duas compactacoes opcionais como experimento revisavel; o ganho isolado e pequeno demais para justificar promessa de economia relevante ou mudanca na instalacao. A capacidade da #172 continua sendo a referencia.

O proximo trabalho de maior potencial e **representar o contexto recuperado sem repetir os mesmos dados entre turnos, tarefas e estrategias**, preservando proveniencia, URLs, alvos e restricoes. Antes de reduzir texto, separar o orcamento de avisos obrigatorios do orcamento de dados auxiliares, cobrindo o limite reproduzido. Depois, testar modulos de instrucoes por dominio usando o Router existente, com regras globais de seguranca integrais e tarefas que mudam de dominio. Essas mudancas sao de risco maior que remover espacos JSON e precisam de comparacoes proprias, sem assumir economia antecipada.

Uma eventual etapa Live devera comparar a mesma tarefa concluida, somar planejador e revisores, alternar ordem de versoes, separar cache frio/quente e registrar `usage` individual. Continua dependendo de **nova autorizacao explicita**; o orcamento antigo da #173 nao foi reutilizado.

## Reproducao offline

Preparar tiktoken 0.12.0 e seu encoding em diretorio auxiliar isolado; apontar PYTHONPATH/TIKTOKEN_CACHE_DIR para esses diretorios. Nao instalar globalmente nem mudar configuracao pessoal. Com checkout separado da #172:

```powershell
py -3.13 scripts/diagnosticos/offline_python.py scripts/diagnosticos/context_audit.py --base C:/caminho/checkout-172 --output C:/caminho/evidencias-novas
py -3.13 scripts/diagnosticos/offline_python.py scripts/diagnosticos/context_audit_summary.py C:/caminho/evidencias-novas
py -3.13 scripts/diagnosticos/offline_python.py scripts/diagnosticos/context_inventory.py --output C:/caminho/inventario.json
py -3.13 scripts/diagnosticos/offline_python.py -m pytest tests/test_context_encoding.py -q
```

O runner nao tem opcao paga, nao constroi cliente OpenAI e substitui todos os handlers terminais. Dependencias auxiliares sao somente de diagnostico; o runtime nao ganhou dependencia externa.
