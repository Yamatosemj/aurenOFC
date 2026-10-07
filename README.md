# Auren

Assistente desktop/voz para Windows, versão técnica **V47**, usando o modelo configurado em `config.py` (snapshot atual: `gpt-5.6-luna`).

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

- **48 tools** no registry/contratos atuais
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
