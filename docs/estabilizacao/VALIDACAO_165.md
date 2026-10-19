# Validação da candidata #165 e preparação isolada

Base verificada no GitHub: PR #165 aberta, draft, sem merge, HEAD
`05f3ea55769123207f17d8365c385b08cff72a39`, branch
`estabilizacao/usabilidade-offline-20261018`. Main remota permaneceu em
`70b040d6191237e2f0a291a14b8ea8fb4b78a09d`. Esta correção fica na branch
`validacao/candidata-165-offline`, descendente da #165. Nenhuma mudança em
Harness, Router, provider, ferramentas, permissões, evidências ou checkpoints.

## CI Windows e Linux: pendente, não aprovado

Foi tentado o workflow existente `auren-manual-tests.yml`, que tem matriz
`ubuntu-latest`/`windows-latest`, na branch exata da #165:

```powershell
& 'C:\Program Files\GitHub CLI\gh.exe' workflow run auren-manual-tests.yml --repo Yamatosemj/aurenOFC --ref estabilizacao/usabilidade-offline-20261018
```

A conexão à API do GitHub foi bloqueada pelo sistema: `connectex: An attempt
was made to access a socket in a way forbidden by its access permissions`.
O conector disponível consulta runs, mas não oferece `workflow_dispatch`; o
portal Maestri não está disponível. A consulta posterior encontrou zero runs
para o HEAD. **O workflow não chegou a ser iniciado.** Não foi alterada a
política de rede, autorização, workflow, runner ou credencial para contornar
o bloqueio. Não há resultado Windows/Linux hospedado desta etapa.

O acionamento deve ser feito em uma sessão com acesso ao GitHub. Para a
candidata atualizada, escolha a branch `validacao/candidata-165-offline` no
[workflow manual](https://github.com/Yamatosemj/aurenOFC/actions/workflows/auren-manual-tests.yml),
ou use:

```powershell
gh workflow run auren-manual-tests.yml --repo Yamatosemj/aurenOFC --ref validacao/candidata-165-offline
gh run list --repo Yamatosemj/aurenOFC --workflow auren-manual-tests.yml --branch validacao/candidata-165-offline --event workflow_dispatch --json databaseId,headSha,status,conclusion
gh run view ID_DO_RUN --repo Yamatosemj/aurenOFC --json headSha,conclusion,jobs
```

Compare `headSha` com o HEAD final da PR de entrega e confira **os dois jobs**,
JUnit e contagens. Um run antigo/sucesso de outro SHA não aprova esta candidata.
Esses comandos acionam pytest hospedado, não testes Live/modelo.

## Testes e correção comprovada

A bateria representativa inicial teve **121 aprovados, nenhuma falha**:
conversa/Router; descoberta e abertura com subprocessos simulados; arquivo
fictício real; Chromium/DOM reais com requests interceptados; composição
fábrica/HTTP; tarefa composta; falha/recuperação; persistência/retomada; eventos
de progresso, cancelamento e geração da sessão. Modelo e efeitos Windows foram
simulados. Não houve abertura de aplicativos pessoais ou navegação externa.

O pacote anterior estava íntegro: 257 hashes conferidos, source_commit da
#165 correto e SHA-256
`3571745d414fb77cf35064ab8fb539ce876fa58358b4c00d14f52461e01c826f`.
Mas **não incluía `pytest.ini`**. A execução numa subpasta de outro checkout
podia herdar configuração/cache do ancestral, explicando o aviso da #165.

Uma regressão constrói ZIP real em repositório fictício, exige configuração
própria, confere manifesto/hashes e exclusão de `.env`, bancos, logs, perfil e
Electron. **Falhou antes da correção e passou depois.** O empacotador agora
inclui `pytest.ini`; as instruções incluem dependências e benchmarks. Não se
modificou configuração global do pytest nem se eliminou teste existente.

Suíte completa final, SHA efetivo, extração/startup do pacote e contagens ficam
na descrição da PR de entrega. Os relatórios JUnit locais ficam em `reports/`.

## Desempenho: comparação com a coleta da #165

Mesmo benchmark, Windows/Python 3.13.15, 100 mensagens sequenciais por cenário,
provider fictício imediato e SQLite real; não mede modelo real. O runtime da
#165 não foi alterado nesta etapa. Resultados sem exclusão de outliers:

| Cenário | Mediana anterior → nova (ms) | p95 anterior → novo (ms) | Chamadas simuladas |
| --- | --- | --- | --- |
| Saudação | 80,035 → 58,522 | 108,647 → 68,479 | 100 → 100 |
| Conversa aberta | 88,501 → 57,516 | 111,679 → 67,542 | 100 → 100 |
| Explicação conceitual | 63,547 → 57,145 | 83,192 → 64,629 | 100 → 100 |

Schemas e payloads permanecem idênticos: zero/1.568 caracteres em saudação,
49/26.055 em conversa aberta e zero/1.776 em explicação. O fallback ambíguo
continua com 49 ferramentas. A busca sintética conserva um subprocesso:
mediana 2,446 → 2,648 ms, p95 2,837 → 3,000 ms, com custo artificial de 2 ms.
Para 100 tarefas antigas, 30 pares WAITING/RUNNING: mediana 8,875 → 5,164 ms,
p95 11,150 → 5,791 ms. Sem descarte de amostras.

**A nova coleta é menor em vários cenários, mas não demonstra nova otimização**:
o código de execução é o mesmo. Ambiente/disco/agendamento variam. Não se
atribui o resultado à correção do pacote, nem se afirma latência menor de API.
[Benchmark](validacao-165/benchmark.json),
[persistência](validacao-165/persistencia.json) e
[referência #165](usabilidade-offline/after.json).

## Dependências e limites

Verificação por metadados locais, sem criar cliente/modelo:

| Dependência | requirements.txt | Instalada |
| --- | --- | --- |
| openai | 3.26.0 | **3.15.0 — divergente** |
| playwright | 1.63.0 | 1.63.0 |
| jsonschema | 4.26.0 | 4.26.0 |
| Pillow | 12.3.0 | 12.3.0 |
| pytest (bateria) | 9.1.1 no CI | 9.1.1 |
| numpy (suíte completa) | 2.5.3 no CI | 2.5.3 |

Não havia wheel local de openai no cache consultado. Não se instalou pacote,
não se alterou o Python global nem se rebaixou o pin para fazer a validação
parecer completa. Os testes substituem o transporte/cliente do modelo; sua
aprovação **não comprova openai 3.26.0 nem o provider real**. O CI pendente deve
conferir instalação com os pins. O ZIP é fonte, não inclui Python/dependências.
[Integridade e versões](validacao-165/integridade-dependencias.json).

Continuam pendentes: CI hospedado; ambiente com todos os pins; resposta e
latência do modelo real; abertura/prontidão de aplicativos reais; episódio
Relógio; qualidade humana do Chrome e tarefas prolongadas. Zero chamadas Live,
sem uso de credenciais de modelos e sem renovação da autorização esgotada.

## Roteiro exato no Windows

Extraia o ZIP em **pasta nova**, sem copiar dados da instalação atual. Abra o
PowerShell na pasta `AUREN_CANDIDATA`. Neste PC, o executável Python encontrado
foi o seguinte; ajuste somente se sua instalação estiver em outro caminho:

```powershell
$aurenPython = 'C:\Users\victo\AppData\Local\Programs\Python\Python313\python.exe'
& $aurenPython --version
& $aurenPython -c "from importlib.metadata import version; print({n: version(n) for n in ('openai','playwright','jsonschema','Pillow','pytest')})"
```

Use ambiente exclusivo com os pins de `requirements.txt` antes de avaliar o
provider real. Se faltar pacote ou houver versão divergente, registre a
pendência; não use instaladores globais ou credenciais para contorná-la. O
`py -3` desta sessão não encontrou Python; o caminho completo evita depender
desse registro. Nenhum componente é baixado pelos comandos abaixo.

Teste os fluxos offline e seus resultados:

```powershell
& $aurenPython scripts/diagnosticos/offline_python.py -m pytest -q tests/test_application_discovery_latency.py tests/test_usability_router.py tests/test_usability_recovery.py tests/test_sqlite_connection_lifecycle.py tests/test_task_persistence_cost.py tests/test_current_task_evidence.py tests/test_offline_browser_usability.py tests/test_chrome_progress_delivery.py
& $aurenPython scripts/diagnosticos/offline_python.py scripts/diagnosticos/benchmark_usabilidade.py --samples 100 --output reports/avaliacao.json
& $aurenPython scripts/diagnosticos/offline_python.py scripts/diagnosticos/benchmark_persistencia.py --output reports/persistencia.json
```

Conferir: nenhuma falha; uma chamada simulada por conversa simples; descoberta
com um subprocesso; nenhuma repetição depois de falha definitiva; evidências
e checkpoints preservados; texto final inteiro e progresso da geração atual.
Chromium ausente pode resultar em skip, que deve ser registrado como pendente.
No checkout Git completo, a suíte final é `offline_python.py -m pytest -q`.
No pacote mínimo, use a seleção acima; documentos históricos/workflows omitidos
fazem alguns verificadores estáticos da suíte completa dependerem do checkout.

**Avaliação com IA real permanece para etapa posterior com nova autorização.**
Somente nessa etapa, o comando de inicialização direta é:

```powershell
& $aurenPython -m ui.chrome_server
```

O módulo abre a interface local Chrome; Ctrl+C encerra o servidor. Não o use
agora para enviar pedidos ao modelo. O futuro roteiro humano, em conversa nova
e arquivos fictícios, é: saudação; pergunta sem ferramentas; leitura de um TXT;
duas leituras e soma; consulta de estado; abertura de aplicativo de teste;
programa inexistente; permissão negada; cancelamento e retomada. Registre tempo
até primeiro progresso, resposta completa, ferramentas/revisões e resultado
comprovado. Observe que negar permissão não deve provocar outro efeito, e
retomar não deve repetir ação incerta. A instalação atual permanece separada.

Esta entrega é candidata para avaliação posterior, não aprovação de uso diário.
