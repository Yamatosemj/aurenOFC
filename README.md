# Auren

Assistente desktop/voz para Windows, versão técnica **V47**, usando o modelo configurado em `config.py` (snapshot atual: `gpt-5.6-luna`).

> **Estado atual do projeto:** consulte [AUREN_STATE.md](AUREN_STATE.md) antes de iniciar qualquer tarefa. É um resumo operacional curto, com referência ao último snapshot verificado; confira PRs, HEAD e CI atuais no GitHub. O histórico acumulado foi preservado separadamente.

## Para continuar a manutencao

- [`AGENTS.md`](AGENTS.md) — regras para IAs e mantenedores: escopo, seguranca, testes e documentacao.
- [`docs/INVENTARIO.md`](docs/INVENTARIO.md) — mapa dos subsistemas e auditorias 0–10. **Documentado não significa validado em hardware.**
- [`docs/history/AUREN_STATE_SNAPSHOT_2026-10-10.md`](docs/history/AUREN_STATE_SNAPSHOT_2026-10-10.md) — histórico integral anterior à consolidação; **não usar como estado operacional atual**.
- [`docs/architecture/01-nucleo.md`](docs/architecture/01-nucleo.md) — auditoria estatica do Harness, orquestradores, estados de tarefa, rastreio, testes e limites conhecidos.
- [`docs/architecture/02-roteamento-seguranca.md`](docs/architecture/02-roteamento-seguranca.md) — auditoria estática do Router, Dispatcher, contratos de ferramentas, políticas de confirmação, anti-loop e conteúdo não confiável.
- [`docs/architecture/03-modelo-sessao-memoria.md`](docs/architecture/03-modelo-sessao-memoria.md) — provider, contexto, SQLite, isolamento por chat, cache e limites reproduzidos.
- [`docs/architecture/04-windows-arquivos-visao.md`](docs/architecture/04-windows-arquivos-visao.md) — Windows/UIA, leitura de arquivos, políticas de caminhos e geometria de visão.
- [`docs/architecture/05-navegador-browser-intelligence.md`](docs/architecture/05-navegador-browser-intelligence.md) — Playwright, leitura do DOM, abas, ações, permissões e limites da verificação posterior.
- [`docs/architecture/06-voz-stt-tts.md`](docs/architecture/06-voz-stt-tts.md) — entrada PTT, captura/VAD, transcrição Parakeet, síntese Kokoro, confirmações por voz e limites de teste.
- [`docs/architecture/07-interface-desktop-gui.md`](docs/architecture/07-interface-desktop-gui.md) — Tkinter, worker/filas, modos Ativo/Standby/Desligado, confirmação, sessão e cancelamento.
- [`docs/architecture/08-skills-capacidades-extensibilidade.md`](docs/architecture/08-skills-capacidades-extensibilidade.md) — carregamento local de skills, catálogo de capacidades, atalhos, flags experimentais e limites de segurança.
- [`docs/architecture/09-testes-ci-controle-remoto.md`](docs/architecture/09-testes-ci-controle-remoto.md) — matriz de testes, CI hospedado, runner Windows, validação de PR via comentário, watchdog e evidências reais.
- [`docs/architecture/10-entradas-config-instalacao-distribuicao.md`](docs/architecture/10-entradas-config-instalacao-distribuicao.md) — canais de entrada, Python escolhido por cada atalho, variáveis, dependências, instalação, dados e limites de distribuição.
- [`docs/TESTES_GITHUB.md`](docs/TESTES_GITHUB.md) e [`docs/CONTROLE_REMOTO_GITHUB.md`](docs/CONTROLE_REMOTO_GITHUB.md) — operação e histórico dos testes remotos, com [evidência de pytest por comentário já executado no Windows](https://github.com/Yamatosemj/aurenOFC/actions/runs/38085000162); consulte sempre o SHA e a política local vigentes.

A documentacao evolui em PRs pequenas por subsistema. Para decidir o status real de uma funcionalidade, confronte documentos com codigo, PRs e CI atuais.

**Correcao candidata do contrato de processos (auditoria de 15/10, achado 2):** as ferramentas `listar_processos_windows` e `encerrar_processo_windows` passam a devolver `ToolResult.success/failure` em **todos** os caminhos, com codigo de erro estruturado para falhas. Falhas nao dependem mais de reconhecer palavras como "nao consegui" e chegam assim ao Dispatcher/Harness. Mensagens de listagem bem-sucedida continuam no mesmo formato; `taskkill` bem-sucedido continua significando **pedido enviado, nao encerramento comprovado**. A adaptacao textual de **outras** ferramentas legadas por `from_legacy` segue como divida tecnica separada; nao ha mudanca global na interpretacao textual.


## Estrutura

```text
agent/       orquestração e componentes Ari adaptados
experimental/ componentes fora do runtime normal
core/        contratos, roteamento, Harness, memória, visão e permissões
memory/      persistência SQLite
providers/   provider do modelo
skills/      carregamento de skills (nomes/caminhos locais validados; SKILL.md tratado como dado nao confiavel)
tools/       capacidades executáveis
voice/       STT/TTS/entrada de voz
tests/       suíte pytest
```

## Atalhos e utilitarios

Arquivos de comando para Windows agora estao organizados por finalidade em `scripts/`:

- `scripts/iniciar/ABRIR_AUREN_GUI.bat` — abrir a interface (uso recomendado)
- `scripts/iniciar/AUREN_VOZ.bat` — abrir o modo de voz
- `scripts/instalar/` — instalar dependencias gerais e de voz
- `scripts/testar/` — executar baterias de teste; `TESTAR_AUREN.bat` sem argumentos usa **somente L0,L1**, sem acionar automaticamente L2/L4/L5. Camadas Live devem ser pedidas explicitamente (`--camada` ou `--completo`) e podem alterar o Windows/usar API.
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

## Interface local no Chrome (candidata)

Para abrir o novo visual de orbe inspirado no protótipo fornecido pelo proprietário, no Windows execute:

```powershell
scripts/iniciar/AUREN_CHROME.bat
```

O atalho usa o seletor compartilhado `scripts/lib/SELECIONAR_PYTHON.cmd` para iniciar `-m ui.chrome_server`, preferindo `.venv` do projeto, depois a `.venv` da pasta pai, depois `py -3` e por último `python`. O servidor inicia em **127.0.0.1**, numa porta livre, e abre o **Google Chrome** quando instalado, usando o navegador padrão como alternativa. O terminal precisa continuar aberto. Não é site na internet, não funciona no celular/rede local e não requer novas bibliotecas Python.

O orbe, os estados e a aparência azul/lilás foram adaptados do arquivo HTML de referência do usuário; a animação **WebGL 3D original** foi restaurada, incluindo shaders, deformações, partículas e anéis, com **Three.js r128 armazenado localmente** (MIT, `ui/vendor/`) sem scripts externos. A página começa **Desligada**, mas **não exige seleção manual de estado**: clique no orbe e envie a primeira mensagem para ligar o Auren automaticamente. Enquanto conversa, fica **Ativo**; após **2 minutos sem novas mensagens ou tarefas em execução**, entra em **Standby** preservando a sessão; a próxima mensagem o reativa. Digitar **`sair`** (ou **`desligar auren`**) encerra a sessão do Harness e mostra **Desligado**. Outra mensagem inicia uma nova sessão. O cabeçalho exibe o estado, mas não oferece botões para alterá-lo. Ativo, Standby e Desligado usam o mesmo `AurenUiWorker` e o mesmo Harness da GUI Tkinter; ações sensíveis exibem Autorizar/Negar na página. Confirmar no navegador **não bypassa** `PermissionManager`. Nada é executado pela página sem passar pelo worker/Harness/Dispatcher.

Limitações: somente texto por enquanto (sem integrar PTT, STT ou TTS); cartões reais de lembretes/agenda ainda não conectados; **`sair` desliga a sessão do Harness, não o servidor HTTP local nem a janela do Chrome**; fechar o Chrome também não encerra automaticamente o servidor; controles no navegador afetam a sessão do Auren e devem ser usados apenas pelo usuário local. Se a janela não abrir automaticamente, copie a URL **127.0.0.1** exibida no terminal. `Ctrl+C` encerra o serviço. O WebGL pode exigir aceleração de hardware ativa no Chrome; a aparência, o desempenho e o funcionamento com API/Chrome/Windows reais ainda precisam de validação no PC pessoal; testes de CI exercitam backend HTTP e mocks, não o hardware.

A GUI Tkinter original continua disponível em `scripts/iniciar/ABRIR_AUREN_GUI.bat` e não foi removida.

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

A camada de voz usa dependências separadas de `requirements-voice.txt`. Reinstalar com `INSTALAR_VOZ.bat` **preserva os modelos ASR/TTS já baixados**: o instalador não limpa `data/voice/`. No primeiro uso, o Parakeet verifica a presença dos arquivos necessários e tenta completar o download se faltar algo; isto pode exigir internet.

**Atenção:** os instaladores não criam automaticamente `.venv`. O atalho da GUI usa `py -3`/`python` global mesmo quando existe uma `.venv`, enquanto o de voz prefere `.venv` e depois `py -3`. Use o [guia técnico da Etapa 10](docs/architecture/10-entradas-config-instalacao-distribuicao.md) antes de diagnosticar erro de dependência. A instalação de `playwright` via pip não instala automaticamente o Chromium.

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

Por padrão, o Auren usa `gpt-5.6-luna`. `config.py` lê `AUREN_MODEL` e usa o padrão quando o valor está vazio ou contém apenas espaços.

**Correção candidata (auditoria, achado 4):** `AUREN_MODEL` passa a determinar o modelo usado pela fachada, pelo prompt e pelo provider, preservando a verificação de versão e o literal do modelo **padrão** para verificadores estáticos antigos. O identificador configurado deve ser de um modelo acessível à conta/API; **nenhuma chamada real à API foi validada**. O modelo padrão permanece `gpt-5.6-luna`; veja [a auditoria de modelo e memória](docs/architecture/03-modelo-sessao-memoria.md).

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
