# Auren

Assistente desktop/voz para Windows, versão técnica **V51**, usando o modelo configurado em `config.py` (snapshot atual: `gpt-5.6-luna`).

> **Estado atual do projeto:** consulte [AUREN_STATE.md](AUREN_STATE.md) antes de iniciar ou continuar trabalho no Auren. O estado oficial registra a tarefa ativa, PRs em andamento, CI, próxima fase e backlog.

## Estrutura

```text
agent/       orquestração e componentes Ari adaptados
experimental/ componentes fora do runtime normal
core/        contratos, roteamento, Harness, memória, visão e permissões
memory/      persistência SQLite
providers/   provider do modelo
skills/      carregamento de skills
tools/       capacidades executáveis
voice/       STT/TTS/entrada de voz
tests/       suíte pytest
```

## Executar

```powershell
python main.py
```

ou

```powershell
python auren.py
```

Para voz:

```powershell
AUREN_VOZ.bat
```

## Instalação

```powershell
INSTALAR_AUREN.bat
INSTALAR_VOZ.bat
```

A camada de voz usa dependências separadas de `requirements-voice.txt`.

### Modelo

Por padrão, o Auren usa `gpt-5.6-luna`. Para testar outro modelo sem alterar o código, defina a variável de ambiente `AUREN_MODEL` antes de iniciar o processo.

PowerShell:

```powershell
$env:AUREN_MODEL = "gpt-5.6-luna"
python main.py
```

Um valor vazio ou composto apenas por espaços volta automaticamente ao modelo padrão.

## Testes

```powershell
py -m pytest -q
python testes_auren_live.py --rapido
python testes_auren_live.py --completo

# compatibilidade com o comando legado
python testes_auren.py --rapido
```

A suíte pytest é a validação automatizada do runtime e roda no CI. O pytest é configurado para procurar testes somente em `tests/`, portanto `testes_auren_live.py` **não faz parte da coleta do pytest** e deve ser executado manualmente.

`testes_auren_live.py` é o **runner live/manual** do Auren: ele pode consumir a API e provocar efeitos reais no Windows, navegador e outras ferramentas. Use-o quando quiser validar o comportamento integrado em um ambiente Windows real.

`testes_auren.py` permanece apenas como fachada de compatibilidade para o comando antigo.

Os resultados gerados por `testes_auren_live.py` ficam em:

```text
logs/testes/RESULTADO_TESTE_AUREN.txt
```

## Inteligência de Arquivos (V47)

A capacidade de arquivos mantém `buscar_arquivo` como busca existente e adiciona duas tools pelo mesmo Dispatcher, contratos e permissões:

- `inspecionar_arquivo`: metadados, tipo detectado, tamanho, datas, SHA-256, estado e evidências locais de origem. Pode procurar cópias confirmadas por hash.
- `ler_arquivo`: leitura controlada de `.txt`, `.md`, `.json` e `.csv`, com encoding detectado e continuação por trechos.

Origem e histórico são tratados como evidência: Zone.Identifier/URL só são reportados quando acessíveis; relação entre cópias é confirmada por SHA-256; trajetória completa permanece desconhecida. PDF pode ser identificado por assinatura, mas leitura de conteúdo ainda não está implementada. DOCX, XLSX e OCR continuam fora do escopo desta etapa.

## Plugins de ferramentas (V48)

Ferramentas locais podem ser adicionadas em `plugins/*.py` sem editar o runtime existente. Um plugin declara `TOOL`, `CAPABILITY`, `DEPENDENCIAS` e um handler que devolve `ToolResult`.

A descoberta faz preflight estatico para plugins desativados, verifica dependencias com `importlib.util.find_spec` antes do import e rejeita nomes duplicados ou reservados pelas tools nativas. Falhas de um plugin isolado nao derrubam o boot.

Todo plugin ativo e registrado simultaneamente no registry de tools, no registry de contratos, no registry de capacidades e no Dispatcher. A execucao continua sendo somente `Router -> Dispatcher -> Contrato -> Permissao -> Ferramenta -> ToolResult`.

Por seguranca, plugin novo entra em `CONFIRM`. A aprovacao fica em `plugins_aprovados.json`, arquivo local ignorado pelo Git. Alterar `habilitado` e chamar `auren.recarregar_plugins()` liga/desliga sem reiniciar; alterar `aprovado` muda o nivel entre `CONFIRM` e `AUTO` sem reiniciar.

O retorno de plugin e marcado como conteudo nao confiavel, assim como leituras de pagina/arquivo. Isso nunca concede permissao para outra acao.

Use `plugins/_template.py` como modelo e `plugins/hora_atual.py` como exemplo completo.

## Lembretes (V49)

O Auren possui tres tools de lembretes pelo mesmo Dispatcher: `criar_lembrete`, `listar_lembretes` e `cancelar_lembrete`.

`criar_lembrete` registra o lembrete no Agendador de Tarefas do Windows como uma tarefa de disparo unico. O XML usa horario local em ISO-8601, execucao como usuario interativo e nivel de privilegio minimo. O comando agendado e uma lista de argumentos que chama o proprio modulo `tools.reminders`; nao ha `shell=True`.

A mensagem fica em metadata local em `%APPDATA%\Auren\lembretes.json` por padrao. O scheduler permanece sendo a fonte do disparo: o Auren nao precisa ficar aberto para o processo agendado chamar o runner.

Criar e cancelar sao acoes persistentes e exigem **CONFIRM**. Listar e somente leitura e fica em **AUTO**. O resultado de criacao inclui o ID do lembrete e o cancelamento como reversao natural da criacao.

O runner interno aceita somente `--disparar <id>`, recupera a mensagem pelo ID e envia uma notificacao no Windows. Depois de uma notificacao bem-sucedida, o agendamento e a metadata sao removidos porque o lembrete e de ocorrencia unica.

A implementacao nao adiciona dependencia externa e e limitada ao Windows/Agendador de Tarefas.


## Pesquisa web (V50)

O Auren possui a tool `pesquisar_web(consulta, modo)`, registrada no mesmo Registry, Contrato, Router, Dispatcher e PermissionManager das demais ferramentas.

Modos disponíveis:
- `news`: prioriza notícias e informação recente
- `research`: prioriza pesquisa mais profunda e fontes técnicas/institucionais
- `price`: prioriza preços, disponibilidade, moeda e atualidade
- `compare`: estrutura a busca para comparação entre opções

A implementação usa o **web search hospedado do Responses API** do provedor OpenAI, sem criar um executor paralelo de navegador. Para tarefas interativas, o modelo continua podendo escolher as ferramentas Browser existentes. A API de web search pode devolver a lista completa de fontes consultadas quando solicitada por `include=["web_search_call.action.sources"]`.

Os resultados de busca são sempre tratados como **conteúdo não confiável**. A ferramenta limita a oito fontes, cerca de 600 caracteres por trecho e aproximadamente 5000 caracteres no conjunto devolvido. Conteúdo externo nunca pode autorizar uma ação por si só.

A política é somente leitura (**AUTO**). Não há dependência nova.


## Continuidade proativa (V51)

Na abertura, o Auren pode apresentar uma frase curta sobre a sessão anterior usando os turnos persistidos da Tarefa 5. O resumo é consumido atomicamente quando apresentado, portanto a mesma frase não volta a aparecer em uma abertura futura.

O monitoramento de tópicos é **desligado por padrão**. Tópicos podem ser configurados sem ativar o recurso. Quando ativado, a infraestrutura persiste a trava de **uma checagem por dia** e oferece estado explícito para desligamento. Não existe monitoramento silencioso ou contínuo.

O projeto atual não possui uma UI gráfica própria de configurações; por isso, os controles ficam expostos como capacidades do próprio Auren, passando pelo Router, Dispatcher, Contrato e PermissionManager. Uma UI futura pode consumir o mesmo estado sem criar outro caminho de execução.

## Arquitetura atual

```text
Entrada
  -> Harness
  -> Orchestrator
  -> Router
  -> OpenAIProvider
  -> function_call
  -> Dispatcher
  -> Contrato
  -> Permissao
  -> Ferramenta
  -> ToolResult
  -> Harness
```

O Router escolhe o conjunto de ferramentas da rodada. Toda execução de ferramenta passa pelo Dispatcher, validação de contrato e permissões antes de chegar ao executor. O resultado estruturado volta ao Harness como `ToolResult`.

## Visão e coordenadas

A captura de tela informa a área de trabalho virtual do Windows, incluindo origem e dimensões. Quando a imagem enviada ao modelo é comprimida ou redimensionada, o Harness transporta a geometria efetivamente entregue e as escalas necessárias para converter pontos observados na imagem para coordenadas da área de trabalho virtual. A camada de Windows usa um contexto DPI por monitor quando disponível para manter a leitura da tela e as coordenadas de entrada no mesmo referencial físico. Conversões com proporção incompatível são rejeitadas em vez de produzir cliques silenciosamente deslocados.

## Estado importante

- **57 tools nativas** no registry/contratos + plugins locais dinamicos
- memória persistente em SQLite
- browser e automação Windows integrados
- visão pode observar a tela, executar clique ou arraste global do mouse com confirmação, manter a geometria da captura e da imagem entregue ao modelo e verificar o estado final em tarefas visuais compostas
- voice local-first para ASR/TTS
- `experimental/wake_word.py` existe, mas não faz parte do caminho normal de voz atual (PTT/F8)
- componentes históricos e relatórios antigos não fazem parte deste pacote runtime

## Licença

Os componentes derivados/adaptados do Ari-VoiceCommand estão cobertos por `LICENSE_ARIVC_MIT.txt`.

## Histórico

A documentação de versões anteriores foi retirada do pacote principal para manter a raiz limpa. Ela deve ser mantida separadamente, fora do runtime.
