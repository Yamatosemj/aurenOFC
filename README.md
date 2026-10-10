# Auren

Assistente desktop/voz para Windows, versão técnica **V47**, usando o modelo configurado em `config.py` (snapshot atual: `gpt-5.6-luna`).

> **Estado atual do projeto:** consulte [AUREN_STATE.md](AUREN_STATE.md) antes de iniciar ou continuar trabalho no Auren. O estado oficial registra a tarefa ativa, PRs em andamento, CI, próxima fase e backlog.

## Para continuar a manutencao

- [`AGENTS.md`](AGENTS.md) — regras para IAs e mantenedores: escopo, seguranca, testes e documentacao.
- [`docs/INVENTARIO.md`](docs/INVENTARIO.md) — mapa dos subsistemas e ordem das auditorias. **Mapeado nao significa auditado ou validado em hardware.**
- [`docs/architecture/01-nucleo.md`](docs/architecture/01-nucleo.md) — auditoria estatica do Harness, orquestradores, estados de tarefa, rastreio, testes e limites conhecidos.
- [`docs/architecture/02-roteamento-seguranca.md`](docs/architecture/02-roteamento-seguranca.md) — auditoria estática do Router, Dispatcher, contratos de ferramentas, políticas de confirmação, anti-loop e conteúdo não confiável.
- [`docs/TESTES_GITHUB.md`](docs/TESTES_GITHUB.md) e [`docs/CONTROLE_REMOTO_GITHUB.md`](docs/CONTROLE_REMOTO_GITHUB.md) — operacao e historico dos testes remotos; **algumas instrucoes antigas aguardam reconciliacao** com os runs atuais.

A documentacao evolui em PRs pequenas por subsistema. Para decidir o status real de uma funcionalidade, confronte documentos com codigo, PRs e CI atuais.

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

## Atalhos e utilitarios

Arquivos de comando para Windows agora estao organizados por finalidade em `scripts/`:

- `scripts/iniciar/ABRIR_AUREN_GUI.bat` — abrir a interface (uso recomendado)
- `scripts/iniciar/AUREN_VOZ.bat` — abrir o modo de voz
- `scripts/instalar/` — instalar dependencias gerais e de voz
- `scripts/testar/` — executar baterias de teste
- `scripts/diagnosticos/` — inspecionar microfones, metricas, custos e outros diagnosticos
- `scripts/experimentos/` — ativar ou desativar experimentos locais

Os `.bat` sempre mudam para a raiz do projeto antes de rodar, mesmo abertos por duplo clique a partir da subpasta.
Os scripts `testes_auren.py` e `testes_auren_live.py` permanecem na raiz como interfaces publicas usadas pelos testes e automacoes existentes, evitando quebrar imports legados.

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
scripts/iniciar/AUREN_VOZ.bat
```

## Interface desktop (primeira versao)

No Windows, abra `scripts/iniciar/ABRIR_AUREN_GUI.bat` (ou rode `python interface_auren.py`).

A interface usa **Tkinter**, que acompanha a instalacao padrao do Python no Windows.
A janela abre em **Desligado**; clique em **Ativo** para enviar mensagens.
**Standby** pausa novos envios e **Desligado** encerra a sessao do Harness.
Ações sensíveis exibem uma janela com **Autorizar / Negar**; se nao houver
resposta, a acao e negada automaticamente. Fechar a janela solicita
cancelamento cooperativo de tarefas em andamento e encerramento da sessao.

A tela **nao usa um segundo executor**: envia mensagens ao `criar_harness()`
existente, portanto Router, Dispatcher, contratos e PermissionManager
continuam sendo o caminho normal. O processamento ocorre numa thread de
trabalho para a janela permanecer responsiva.

**Limites desta versao:** conversa por texto apenas; voz/PTT continua em
`scripts/iniciar/AUREN_VOZ.bat`. Nao ha garantia de cancelamento instantaneo de uma
operacao externa que esteja bloqueada. A interface ainda precisa de um
teste com janela real no Windows; pytest valida o backend e os contratos,
nao a interacao visual. A chave/API ja configurada no sistema continua
necessaria para pedidos ao modelo.

## Instalação

```powershell
scripts/instalar/INSTALAR_AUREN.bat
scripts/instalar/INSTALAR_VOZ.bat
```

A camada de voz usa dependências separadas de `requirements-voice.txt`.

### Evolução de voz V48 (candidata, ainda sem validação física)

O modo de voz em `scripts/iniciar/AUREN_VOZ.bat` usa push-to-talk
**Ctrl direito + Shift direito**, pré-roll/pós-roll de áudio, detecção local de
fala (WebRTC VAD com fallback de energia), tratamento de silêncio e
recuperação de falhas transitórias do microfone. A captura tenta 16 kHz e,
quando o dispositivo não aceita, usa sua taxa nativa; o ASR normaliza para
16 kHz. O dispositivo pode ser indicado por nome em `AUREN_MIC_DEVICE`.

`requirements-voice.txt` inclui `webrtcvad-wheels` em versão fixa.
Os testes pytest simulam captura, VAD, microfones e transcrição; **não**
comprovam qualidade, latência nem PTT com hardware real. A versão estável
do Auren continua V47 até a validação física de voz.


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

- **49 tools** no registry/contratos atuais
- memória persistente em SQLite
- browser e automação Windows integrados
- visão pode observar a tela, executar clique ou arraste global do mouse com confirmação, manter a geometria da captura e da imagem entregue ao modelo e verificar o estado final em tarefas visuais compostas
- voice local-first para ASR/TTS
- `experimental/wake_word.py` existe, mas não faz parte do caminho normal de voz atual (PTT Ctrl direito + Shift direito)
- componentes históricos e relatórios antigos não fazem parte deste pacote runtime

## Licença

Os componentes derivados/adaptados do Ari-VoiceCommand estão cobertos por `LICENSE_ARIVC_MIT.txt`.

## Histórico

A documentação de versões anteriores foi retirada do pacote principal para manter a raiz limpa. Ela deve ser mantida separadamente, fora do runtime.
