# Candidata de estabilização e usabilidade — validação offline

Base: PR #164, `a3896c38e4f3136718ce89852b2c3ff5aa344620`. Ancestralidade
local conferida para os HEADs #161 (`af84aec`), #162 (`84eb9ca`) e #163
(`38e3413`). GitHub consultado: as quatro PRs estavam abertas; main remota
em `70b040d`, CI da #164/run 39151494105 aprovado no próprio SHA. Nenhum merge.
As correções anteriores foram preservadas, sem reaplicação ou Electron.

O repositório original tinha `desktop/` não rastreado e estava em
`desenvolvimento/fase-5-correcoes-live`. Seu `.git` era somente leitura na
sandbox. O trabalho ocorreu em clone local `.work-stabilizacao`, branch
`estabilizacao/usabilidade-offline-20261018`. Não se modificou instalação,
dados pessoais, configuração global ou main. O Python foi invocado por seu
executável 3.13.15; `py -3` não encontrou instalação nesta sessão.

## Diagnóstico do caminho real

Chrome → HTTP local → AurenUiWorker → Harness/TaskManager → planejamento e
SessionContextManager → Router → provider → Harness → revisão de intenção →
Dispatcher/contratos/PermissionManager → executor/ToolResult → evidências e
verificação de conclusão → persistência/resposta → eventos → Chrome.

| Etapa | Evidência e decisão |
| --- | --- |
| Recepção/UI | Polling existente a cada 450 ms; sem garantia de entrega instantânea. `busy` agora informa recebimento; eventos reais distinguem contexto, modelo, intenção, ferramenta autorizada e conclusão. Sem heartbeat fictício. |
| Contexto/memória | 117 traces históricos: contexto mediana 5,298 ms/p95 14,617 ms. Na bateria local, cerca de 3–4 ms. Não se comprovou que recuperação de memória fosse o gargalo principal; seu conteúdo e isolamento foram preservados. |
| Planejamento | Heurístico local, sem chamada adicional de IA. Tempo agora medido no metadata do span de contexto, que **inclui** planejamento; não somar ambos. |
| Tarefas/checkpoints | cProfile na base, 90 mensagens: 630 transições persistidas, 4,269 s acumulados no wrapper; deepcopy 1,592 s e asdict 0,834 s, tempos sobrepostos. O wrapper copiava/serializava o histórico inteiro a cada transição. Agora só os registros alterados são copiados e serializados. Cada commit transacional e validação anterior permanece. |
| Schemas/Router | Saudação carregava 49 schemas. Saudação estrita e uma forma conservadora de explicação conceitual recebem zero ferramentas, mas continuam recebendo resposta do modelo. Pedidos ambíguos e continuações conservam fallback completo; a solicitação seguinte pode ampliar o conjunto. |
| Provider | Default de timeout/retries do SDK era usado fora do modo de teste; agora o cliente recebe timeout de 45 s e zero retries ocultos em todos os modos. Timeout do transporte não é deadline absoluto de toda a tarefa. Respostas com status incompleto/falho não podem executar chamadas parciais nem concluir. |
| Verificações | Revisão de intenção, revisão de conclusão, prova da própria tarefa, budgets e checkpoints mantidos. Acrescentados spans separados das revisões; o contador persistido `TaskSnapshot.model_calls` continua sendo a referência de chamadas reservadas, inclusive revisores. Contador antigo `model_rounds` do trace não deve ser interpretado como inventário completo de tentativas/revisões. |
| Ferramentas Windows | Descoberta recursiva abria um PowerShell por candidato e raiz. Na fixture foram 16, agora 1. PATH é consultado antes da recursão; catálogo StartApps tem cache em memória por 60 s, sem cache de falhas/vazios. UTF-8 explícito no subprocesso e argumentos PowerShell literais preservados. |
| Persistência auxiliar | SQLite com `with connection` não fecha o handle. Memória e trace agora fecham conexões em finally, incluindo rollback/exceções; testes verificam fechamento e rename no Windows. Nenhum banco pessoal foi migrado. |
| Resposta/UI | O texto final já disponível era revelado a 70 ms/palavra: 100 palavras acrescentavam 6.930 ms até exibição completa. Texto agora é publicado inteiro, sem mudar Three.js, layout, estados de sessão ou confirmações. |
| Crescimento | Contexto segue com teto de 3.600 caracteres e estado com 4.500; outputs separados também contam no payload. Não se introduziu cache de respostas entre chats nem resumo destrutivo. A serialização de tarefas antigas deixa de crescer em cada transição, mas o snapshot da tarefa atual ainda cresce com seus passos. |

Métricas novas não armazenam prompts nos metadados: tamanho dos schemas,
tempo de roteamento/provider, tamanho do contexto e tempo de planejamento.
O log existente conserva sua política de redação; não se exportaram conversas.
O campo `provider_ms` mede a fronteira do adaptador, não somente rede/API.

### Histórico, API e caso Relógio

O banco existente foi aberto com SQLite `mode=ro`; exportaram-se apenas
[agregados](usabilidade-offline/history.json). Há 117 tarefas e 297 spans de
modelo: mediana 1.496,103 ms/p95 6.579,493 ms; ferramentas: 188 spans,
mediana 1,979 ms/p95 8.998,366 ms. Para 111 tarefas agentic: total mediana
3.334,815 ms/p95 33.883,285 ms, 297 chamadas contabilizadas no formato antigo.

**A procedência é mista e a versão de cada execução não está gravada.** Esses
dados não permitem separar com rigor mocks, API real, overhead do cliente e
revisores. Não representam benchmark da candidata nem latência pura da API.
Nenhuma nova medição de API foi realizada. O episódio relatado do Relógio de
aproximadamente 36 s não foi localizado nos arquivos históricos disponíveis;
não se atribui sua causa a PowerShell, API ou outra etapa. Há uma causa geral
de trabalho redundante demonstrada pela fixture, mas sua participação naquele
episódio permanece desconhecida.

## Comparação antes/depois

Windows, Python 3.13.15, processos separados, provider fictício imediato,
TaskManager/SQLite/memória/traces reais e arquivos temporários exclusivos.
Cada caso tem 100 mensagens sequenciais no mesmo chat. O número de chamadas
ao provider fictício foi **100 antes e 100 depois em cada caso**; nenhuma foi
substituída por resposta fixa. Resultados sem desconto de outliers:

| Cenário | Mediana total local antes → depois (ms) | p95 antes → depois (ms) | Schemas antes → depois | Payload mediano antes → depois (caracteres) |
| --- | --- | --- | --- | --- |
| Saudação | 79,018 → 80,035 | 92,011 → 108,647 | 49 → 0 | 25.751 → 1.568 |
| Conversa aberta | 74,165 → 88,501 | 107,031 → 111,679 | 49 → 49 | 26.055 → 26.055 |
| Explicação conceitual | 88,615 → 63,547 | 112,869 → 83,192 | 49 → 0 | 25.959 → 1.776 |

**Não houve melhora uniforme de tempo total offline.** A saudação e a conversa
aberta pioraram nesta coleta; não se afirma aceleração geral nem redução da
latência da API por causa dos schemas menores. Execuções anteriores com 30
amostras também variaram. Disco, agendamento e overhead observacional não
foram isolados. A menor carga de schemas é comprovada; seu efeito no modelo
real ainda precisa de validação Live explicitamente autorizada.

No ensaio específico de persistência, 30 pares WAITING/RUNNING por tamanho de
histórico, SQLite real:

| Tarefas antigas | Mediana antes → depois (ms) | p95 antes → depois (ms) |
| --- | --- | --- |
| 1 | 6,841 → 9,018 | 15,737 → 10,811 |
| 30 | 8,238 → 8,882 | 11,077 → 10,585 |
| 100 | 13,832 → 8,875 | 23,587 → 11,150 |

Isso demonstra redução do custo com histórico maior, sem prometer benefício
para histórico curto. `process_time` no Windows teve resolução de 15,625 ms;
medianas de CPU zeradas no JSON não significam custo zero.

Busca de executável com **custo simulado de 2 ms por subprocesso**, 100 amostras:
16 → 1 subprocessos; mediana 40,929 → 2,446 ms, p95 43,179 → 2,837 ms.
Não é tempo de busca real do Windows. O catálogo pode consumir até 12 s e o
subprocesso recursivo até 20 s; varredura Python de atalhos e filesystem lento
continuam sem deadline absoluto. Não se declarou o caso Relógio corrigido.

Dados: [antes](usabilidade-offline/before.json),
[depois](usabilidade-offline/after.json),
[persistência antes](usabilidade-offline/persistence-before.json),
[persistência depois](usabilidade-offline/persistence-after.json).

## Confiabilidade e bateria cotidiana

| Situação | Comportamento/validação offline |
| --- | --- |
| Saudação, conversa, pergunta sem tool | Router real + provider roteirizado; uma chamada, preservando resposta inteligente a cargo do modelo. |
| Abertura de aplicativo | Descoberta/lançamento simulados; timeout, ausência, acesso negado, cache expirado e resultado incerto distintos. Sucesso indica solicitação enviada, nunca janela pronta. |
| Estado Windows | Harness/Dispatcher/PermissionManager reais, handler substituído; não consultou o desktop pessoal. |
| Pesquisa no navegador | Chromium headless real em perfil novo, DOM/Dispatcher reais, todas as páginas interceptadas com dados fictícios; sem pesquisa externa, sem download, sem modelo. |
| Leitura de arquivo | Bateria existente com arquivos reais fictícios, política de caminho e prova da própria tarefa preservadas. |
| Duas ou mais etapas | Fixture integrada existente pela fábrica/HTTP/arquivos reais, revisor de conclusão roteirizado. Retomada entre processos e checkpoint próprio preservados. |
| Ferramenta indisponível/inexistente | `unknown_tool` e `not_implemented` encerram sem inventar capacidade ou autorização expirada. Ferramenta inadequada mantém contrato, revisão de intenção e guarda de evidências existentes. |
| Permissão negada | Para imediatamente, sem nova proposta nem execução do restante do lote. Sem tentar contornar recusa. |
| Falha genérica | Pode seguir o caminho existente de recuperação; a terceira proposta da mesma assinatura após duas falhas é barrada antes do executor. Sucesso de outro alvo não apaga falha. |
| Operação demorada/resultado incerto | Erros de descoberta e lançamento separados. Após tentativa de lançamento com erro não há segundo caminho de lançamento, pois o primeiro efeito pode ter ocorrido. |
| Resposta incompleta | Status incomplete/failed/cancelled/queued/in_progress interrompe antes de executar suas tools; resposta vazia mantém recuperação existente limitada. |
| Falha intermediária | Passos anteriores ficam no histórico; falha definitiva impede efeitos seguintes do lote e conclusão. Não há rollback fictício de efeito externo. |
| Conversa anterior | Testes de continuidade e contexto por chat existentes preservados; resumo retrospectivo não exige releitura artificial. |
| Interrupção/retomada | Suite de persistência, retomada e incerteza existente; novos testes forçam falha de disco durante passo, orçamento, criação e seleção, conferindo rollback e reabertura. |
| Progresso/cancelamento | Eventos vinculados à geração da sessão; evento atrasado descartado. Observador quebrado não altera execução; ferramenta negada não emite evento de execução autorizada. |

A base teve **1.141 aprovados, 8 ignorados** na suíte completa offline local.
Durante o desenvolvimento houve execuções falhas: temporários inacessíveis;
fixtures sob AppData bloqueadas corretamente pela política; cópias de fontes
em reports confundindo verificadores AST; compatibilidade de um trace falso;
expectativa antiga dos defaults do SDK; import direto de ferramenta num
diagnóstico, movido para fixture de teste fora do runtime. As proteções e os
verificadores foram preservados. Somente a expectativa do timeout/retries
normal foi atualizada para o novo comportamento intencional; nenhum teste foi
eliminado. **Resultado final, SHA e situação de CI ficam na descrição da PR**,
evitando commits recursivos apenas para copiar números de runs.

O lançador `offline_python.py` remove credenciais de API do ambiente do filho,
bloqueia sockets Python fora de loopback e usa temporários exclusivos fora
de AppData/árvore de código. Não é sandbox de SO para binários arbitrários.
O teste Chromium intercepta requests e desabilita resolução externa/background.
Fixtures antigas em subprocessos que recompõem o ambiente substituem o
transporte do modelo explicitamente e recusam credenciais. Não se executou
`testes_auren_live.py`, não se renovou a autorização esgotada de 8 chamadas.

## Streaming e limites restantes

Streaming do provider poderia antecipar o primeiro texto, mas hoje o Harness
consome respostas completas, decide tools/revisões e só depois publica a
conclusão. Expor texto antes dessas decisões arriscaria mostrar uma conclusão
que o verificador recusaria. Exigiria eventos de delta identificados por tarefa
e geração, buffering de function_call/reasoning, descarte em erro/cancelamento,
separação entre rascunho e conclusão e testes de reconexão. Benefício depende
do tempo de primeiro token, que não se mede com mock. **Não implementado**;
primeiro foi removido o atraso artificial de exibição e adicionado progresso
real. HTTP continua com polling; não houve reestruturação SSE/WebSocket.

Continuam pendentes: qualidade/latência do modelo real, impacto real da redução
de schemas, descoberta/abertura e prontidão de janelas reais no Windows, caso
Relógio, interação visual humana, tarefas longas, cache de apps recém-instalados
(até 60 s), cancelamento de chamada externa bloqueada e deadline absoluto de
filesystem. Reconhecimento de capacidade ausente em linguagem natural ainda
depende de o modelo explicar corretamente o catálogo; o runtime distingue
erros estruturados, mas não ganhou um interpretador universal de intenções.
Fallback completo permanece para ambiguidades. Alternativas diferentes não
apagam falhas anteriores sem comprovação. Esta é candidata otimizada para
avaliação posterior, **não aprovação para uso diário**.

## Testar no Windows

Extraia o pacote fonte isolado em pasta nova, sem copiar `.env`, `data`, `logs`
ou perfil do navegador da instalação atual. Não há instalador nem substituição
de atalhos. É necessário Python e dependências já disponíveis; a entrega não
instala nem baixa componentes automaticamente.

Na raiz do repositório candidato, usando seu Python 3.13:

```powershell
python scripts/diagnosticos/offline_python.py -m pytest -q
python scripts/diagnosticos/offline_python.py scripts/diagnosticos/benchmark_usabilidade.py --samples 100 --output reports/avaliacao.json
python scripts/diagnosticos/offline_python.py scripts/diagnosticos/benchmark_persistencia.py --output reports/persistencia.json
```

O pacote mínimo inclui código e a bateria focada, mas omite o histórico
documental e workflows; nele use a seleção indicada em `LEIA_PRIMEIRO.txt`.
`py -3` pode ser usado quando corretamente registrado; se não encontrar Python,
invoque o caminho completo do executável instalado. Não execute instaladores
nem scripts Live para contornar dependência ausente.

Para **avaliação prática com modelo real somente após nova autorização
explícita**, o lançador continua `scripts/iniciar/AUREN_CHROME.bat`. Até lá,
fique na bateria offline. Abrir o canal não autoriza consumo de API. Não copie
credenciais para o pacote, não substitua a instalação atual e não altere main.
