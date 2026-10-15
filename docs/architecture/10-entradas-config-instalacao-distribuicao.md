# Arquitetura 10 — Entradas, configuração, instalação e distribuição

> **Etapa 10 — auditoria estática** da `main` em `0392365d609907557006f2e9ab3370857875ea51`, em 2026-10-10. Esta etapa encerra o **inventário inicial de subsistemas documentais**, **não** a validação funcional/Live do Auren. Não se executou instalador, janela, microfone, download, API ou automação no PC pessoal; correções apontadas exigem PR própria.
>
> Consulte [01 — Harness](01-nucleo.md), [03 — Modelo, sessão e memória](03-modelo-sessao-memoria.md), [06 — Voz](06-voz-stt-tts.md), [07 — GUI](07-interface-desktop-gui.md), [09 — Testes e remoto](09-testes-ci-controle-remoto.md) e [estado oficial](../../AUREN_STATE.md).

## 1. Ponto de entrada é canal, não outro cérebro

| Entrada | Comando / lançador | Comportamento real |
| --- | --- | --- |
| Terminal principal | `python main.py` ([`main.py`](../../main.py)) | Importa `auren.iniciar_auren` e o executa. Não faz configurações próprias |
| Terminal alternativo | `python auren.py` ([`auren.py`](../../auren.py)) | Executa exatamente `iniciar_auren()` quando chamado como script |
| GUI Tkinter | `python interface_auren.py` ou [`scripts/iniciar/ABRIR_AUREN_GUI.bat`](../../scripts/iniciar/ABRIR_AUREN_GUI.bat) | Instancia janela em **Desligado**, worker e canal de confirmação GUI; só cria Harness no primeiro pedido |
| PTT/voz | `python voice/main.py` ou [`scripts/iniciar/AUREN_VOZ.bat`](../../scripts/iniciar/AUREN_VOZ.bat) | Inicia captura local, STT Parakeet, TTS Kokoro, entrada textual paralela e canal de confirmação por voz |
| Teste legada | [`testes_auren.py`](../../testes_auren.py) | Fachada para `testes_auren_live.py`, **não** modo normal de atendimento |
| Atalhos de testes | [`scripts/testar/TESTAR_AUREN.bat`](../../scripts/testar/TESTAR_AUREN.bat), [`TESTAR_VOZ.bat`](../../scripts/testar/TESTAR_VOZ.bat) | Runner manual potencialmente Live versus pytest sintético focado; não iniciar como “testes inocentes” sem verificar argumentos |

Todos os canais de conversa reaproveitam o mesmo ponto de montagem `auren.criar_harness(confirmation_channel=...)`; o Harness encaminha as ações pelo **Router → Dispatcher → contrato → PermissionManager → executor → ToolResult**, com contexto/sessão compartilhados na fachada do processo. CLI, GUI e voz **não** são agentes independentes executando tools por caminhos paralelos.

### Particularidades do bootstrap

- [`main.py`](../../main.py) contém apenas import e chamada de `iniciar_auren`. A fachada [`auren.py`](../../auren.py) possui reexports legados e cria globalmente `PermissionManager`, `PersistentMemoryStore` e `SessionContextManager` durante o import. A instância de cliente OpenAI, por outro lado, é criada **sob demanda** pelo provider quando necessária; isso não significa que toda inicialização offline seja garantida.
- [`voice/main.py`](../../voice/main.py) insere a raiz do projeto no `sys.path`, inicia ASR em thread de aquecimento e o PTT. A hotkey em código é **Ctrl direito + Shift direito**, ESC sai. Modelos ASR/TTS podem exigir downloads na primeira utilização. O script de voz imprime `Voice Engine V4` embora os atalhos de voz exibam `V3`: são rótulos desalinhados, **não** três releases distintas.
- [`interface_auren.py`](../../interface_auren.py) cria a janela no thread Tk e passa mensagens a `AurenUiWorker`. **Standby** impede envio pelo campo, mas não suspende execução já em andamento; **Desligado** solicita cancelamento cooperativo. Para os limites completos, veja [Etapa 7](07-interface-desktop-gui.md).

## 2. Configuração e ambiente efetivamente lidos

[`config.py`](../../config.py) define:

| Campo | Valor na revisão | Consequência |
| --- | --- | --- |
| `PROJECT_ROOT` | Pasta que contém `config.py` | Determina paths locais do projeto, não depende da pasta atual do terminal |
| `BROWSER_PROFILE_DIR` | `browser_profile/` | Perfil persistente local do Playwright; ignorado por Git |
| `MEMORY_DB_PATH` | `data/memory/auren_memory.sqlite3` | Caminho da memória local; ignorado por Git |
| `AUREN_VERSION` | **47** | Identificação técnica estável atual, não avaliação do voice V48 |
| `DEFAULT_MODEL` | `gpt-5.6-luna` | Modelo padrão definido no código |
| `MODEL` | `os.getenv("AUREN_MODEL", "").strip() or DEFAULT_MODEL` | Valor efetivo usado por fachada/prompt/provider após correção candidata; aceitação pela API não validada |
| `CACHE_KEY` | `auren-v47` | Namespace de cache derivado da versão |
| `ARCHITECTURE_NAME` | `V47 ARI NATIVE VISUAL GEOMETRY` | Identificação da arquitetura |
| `RESPONSE_CACHE_MAX_ITEMS` e `TTL_SECONDS` | **50 itens**, **600 segundos** | Defaults do cache de resposta textual, não validade de estados do Windows |

**Correção candidata do achado 4:** `auren.py` mantém os literais `AUREN_VERSION=47`, `MODEL="gpt-5.6-luna"`, `CACHE_KEY` e `ARCHITECTURE_NAME` para verificação **estática do modelo padrão** e compatibilidade, mas passa a comparar esse literal com `config.DEFAULT_MODEL` e a usar `config.MODEL` em execução. O prompt anuncia o identificador efetivamente escolhido. Os novos testes de [startup isolado](../../tests/test_model_override_startup.py) cobrem a fachada e requisições simuladas sem rede; modelo externo, API real, custo e funcionamento final ainda exigem avaliação própria.

Outras configurações ambientais no runtime, **com escopo próprio**, incluem `OPENAI_API_KEY` usada pelo SDK (não gravada no repositório), `AUREN_TEST_MODE=1` para limites e confirmações de teste, `AUREN_EXPERIMENT_CAPABILITY_AUDIO` para experimento opt-in, `AUREN_MIC_DEVICE` para captura de áudio, `AUREN_ASR_MODEL` para escolha da origem do modelo STT e `AUREN_TTS_VOICE`/`LANG`/`SPEED` para síntese. Os parâmetros exatos e riscos dessas flags estão nas [Etapas 6](06-voz-stt-tts.md), [8](08-skills-capacidades-extensibilidade.md) e [9](09-testes-ci-controle-remoto.md).

**Não há carregamento automático de arquivo `.env` implementado em `config.py`**; ignorar `.env` no Git **não** equivale a injetar suas variáveis no processo. O usuário/sistema precisa disponibilizar o ambiente por método adequado e seguro; nunca inserir tokens em script versionado ou log público.

## 3. Ambiente Python, dependências e instalação

| Arquivo | Conteúdo fixado | Papel |
| --- | --- | --- |
| [`requirements.txt`](../../requirements.txt) | `openai==3.26.0`, `playwright==1.63.0`, `jsonschema==4.26.0`, `Pillow==12.3.0` | Dependências principais |
| [`requirements-voice.txt`](../../requirements-voice.txt) | `onnx-asr[cpu,hub]==0.12.0`, `kokoro-onnx==0.6.1`, `sounddevice==0.5.6`, `soundfile==0.13.1`, `keyboard==0.13.5`, `numpy==2.5.3`, `webrtcvad-wheels==2.0.14.post1` | Extras de áudio/STT/TTS; não instalados pelo instalador básico |
| [`scripts/instalar/INSTALAR_AUREN.bat`](../../scripts/instalar/INSTALAR_AUREN.bat) | Executa `-m pip install -r requirements.txt` | Usa `.venv` do projeto, depois `..\\.venv`, depois `py -3` ou `python` global; retorna código de saída |
| [`scripts/instalar/INSTALAR_VOZ.bat`](../../scripts/instalar/INSTALAR_VOZ.bat) | Executa `-m pip install -r requirements-voice.txt` | Prefere `.venv` do projeto; senão usa `py -3`. Não instala dependências básicas |
| [`tests/test_dependency_pins.py`](../../tests/test_dependency_pins.py) | Assegura presença de `==` e ausência de versões divergentes entre listas | **Não** prova resolução offline, integridade de pacotes, compatibilidade completa de transitivas nem compatibilidade em toda máquina |

**Diferenças importantes dos instaladores:**

1. **Nenhum desses scripts cria automaticamente uma `.venv`**. Se ela não existir, a instalação pode usar Python global (ou um ambiente de outro escopo, dependendo do comando). O Python escolhido para instalar precisa corresponder ao usado depois para iniciar.
2. O instalador de voz diz **“Limpando apenas cache ASR incompleto”**, mas executa `rmdir /s /q` sobre **todo o diretório de cache ASR especificado se existir**, independentemente do estado; pode exigir novo download. O script **não verifica o código de falha do `rmdir`** e termina imprimindo código zero depois da instalação de pacotes bem-sucedida. Não vender como reinstalação preservadora do cache.
3. Ambos os instaladores apenas usam `pip`; **não** executam a instalação do browser Chromium do Playwright. O pacote Python `playwright` instalado não prova existência do navegador binário, driver/microfone, dispositivos áudio, permissões de UIA ou perfil Windows adequado. Essas pré-condições exigem verificação e orientação específicas numa futura melhoria de onboarding.

O repositório não possui nesta revisão arquivo de build/distribuição como `pyproject.toml`, `setup.py`, instalador MSI ou executável portátil gerado. O processo documentado é **checkout do código-fonte + ambiente Python + scripts de instalação + execução por Python**. Não anunciar um instalador completo “um clique”, serviço Windows ou distribuição em EXE que o código não fornece.

## 4. Comparação dos atalhos de entrada e testes

| Atalho | Escolha real do interpretador | Consequência documentada |
| --- | --- | --- |
| [`ABRIR_AUREN_GUI.bat`](../../scripts/iniciar/ABRIR_AUREN_GUI.bat) | `py -3` se disponível, senão `python` | **Não procura `.venv`**, mesmo que `INSTALAR_AUREN.bat` tenha instalado dependências nela. Pode falhar com `ModuleNotFoundError` usando o Python global |
| [`AUREN_VOZ.bat`](../../scripts/iniciar/AUREN_VOZ.bat) | `.venv\\Scripts\\python.exe` se presente, senão `py -3` | Não testa `..\\.venv` e não oferece fallback `python` sem `py` |
| [`TESTAR_AUREN.bat`](../../scripts/testar/TESTAR_AUREN.bat) | `.venv` local → `..\\.venv` → `py -3` → `python` | Sem argumentos **seleciona `--camada L0,L1,L2,L4`**: inclui **L4 com modelo/API e efeitos reais**, apesar do comentário “regressão diária sem L5”. **Não é pytest de baixo risco** |
| [`TESTAR_VOZ.bat`](../../scripts/testar/TESTAR_VOZ.bat) | `.venv` local, senão `py -3` | Roda somente `pytest tests/test_voice.py -q`. Não prova qualidade física de áudio; **não preserva explicitamente `%ERRORLEVEL%` ao sair** após `pause` |
| [`scripts/diagnosticos`](../../scripts/README.md) | Scripts específicos, alguns Python com bootstrap de raiz | Ferramentas auxiliares para diagnósticos; alguns podem depender de serviços, devices ou API. Checar intenção antes de executar |
| [`scripts/experimentos`](../../scripts/README.md) | Variantes do lançamento de `main.py` com flag de áudio | Opt-in temporário para resolver volume/mídia via Capability; não recurso default |

Todos os arquivos `.bat` estão sob [`scripts/`](../../scripts/README.md) e executam `cd /d "%~dp0..\\.."` na inicialização, logo são independentes da pasta em que o usuário abriu o atalho. **Isso não significa que todos selecionem o mesmo interpretador**. A suíte [`tests/test_scripts_layout.py`](../../tests/test_scripts_layout.py) confere presença, bootstrap de diretório e destinos textuais, mas não instala dependências nem abre uma janela.

**Recomendação documental para manutenção futura:** unificar a escolha de Python entre **instalar, GUI, voz e testes**, preservando compatibilidade e mensagens úteis quando o ambiente não estiver pronto; tratar em PR de código própria, acompanhada de testes Windows reais/simulados. Não corrigir nesta auditoria documental.

## 5. Dados, segredos, caches e atualização

[`.gitignore`](../../.gitignore) exclui ambientes virtuais (`.venv/` etc.), `.env`, cache Python, logs, `runtime/`, `browser_profile/`, `data/memory/`, `data/voice/`, arquivos SQLite/DB, relatórios e artifacts ZIP. **Ignorar arquivos evita o commit acidental habitual, mas não é proteção de acesso ou criptografia.** Também não cobre automaticamente qualquer cópia de segredo feita em pasta inesperada.

Pelo [`config.py`](../../config.py), o banco de memória padrão reside em `data/memory/auren_memory.sqlite3`. O perfil do navegador em `browser_profile/` e o cache de modelos ASR/TTS podem conter dados locais; não colocar esses diretórios em PRs. Em caso de backup ou migração, avaliar separadamente portabilidade, privacidade, incompatibilidade de caminhos e risco de perda de informações. Instalar novamente não deve ser tratado como restauração de banco, sessão ou dados.

O controle remoto [`auren-update-pc.yml`](../../.github/workflows/auren-update-pc.yml) oferece a operação **manual** `atualizar_main` por `git pull --ff-only origin main` após confirmar branch, origin e checkout rastreado sem alterações. **Fazer merge no GitHub não atualiza automaticamente a cópia do Windows pessoal**. A [Etapa 9](09-testes-ci-controle-remoto.md) explica permissão local, SHA e limites. Esta etapa **não** acionou esse workflow, executou `git pull` nem instalou nada no PC.

## 6. Versão, distribuição e garantias que não existem

- **V47:** valor técnico de `config.py` e da fachada, também exposto pela GUI. A candidata de voz **V48 foi incorporada ao código**, porém sem validação de hardware, logo não se deve trocar globalmente o rótulo só para refletir código adicionado.
- **SDK/modelos:** números de versão dos pacotes principais/de voz são fixados, mas isso **não** fixa todas as dependências transitivas em lockfile completo; modelos ONNX e binários externos podem ser baixados separadamente. O teste de pins é sintático.
- **Distribuição:** não há pipeline de release EXE/instalador, update automático, instalador de serviço, migração de memória, auto-configuração de áudio ou promessa de execução sem Python demonstrados neste repositório.
- **Ambiente compatível:** os checks hospedados usam Python **3.13**, Linux e Windows com dependências instaladas durante o workflow; aprovação do CI não comprova periféricos, browser, identidade da API, permissões da GUI ou todos os softwares de um notebook real.
- **Observabilidade:** logs/resultados de uma inicialização e relatório do `testes_auren_live.py` não são equivalentes a um teste real com sucesso de todas as ferramentas; relatar sempre versão, modo de entrada, Python escolhido, SHA e ambiente.

## 7. Validação e limites da auditoria

| Evidência | O que oferece | O que fica pendente |
| --- | --- | --- |
| [`tests/test_model_config.py`](../../tests/test_model_config.py) e [`tests/test_model_override_startup.py`](../../tests/test_model_override_startup.py) | Variável de ambiente, startup de fachada e montagem de requisição simulada | Não verifica disponibilidade/compatibilidade de modelo na API real |
| [`tests/test_dependency_pins.py`](../../tests/test_dependency_pins.py) | Regras de pin direto e deduplicação | Pip install num sistema limpo, transitivas, vulnerabilidades, dependências nativas |
| [`tests/test_scripts_layout.py`](../../tests/test_scripts_layout.py) | Caminhos de launchers e preservação de entradas | Execução real de BAT e instalação/voz/GUI |
| [`tests/test_desktop_ui_backend.py`](../../tests/test_desktop_ui_backend.py) | Contrato simulado de GUI e sintaxe do frontend | Janela Tk física, DPI, foco e política Windows |
| [`tests/test_voice.py`](../../tests/test_voice.py) | Mocks de VAD/STT/TTS | Microfone, downloads, latência e áudio real |
| [`tests/test_live_runner_facade.py`](../../tests/test_live_runner_facade.py) | Fachada legada preservada | Bateria Live real, efeitos/autorizações e API |
| [`pytest.ini`](../../pytest.ini) + CI da PR | Testes hospedeiros em `tests/` | Segurança de todas as instalações, experiência de setup e uso cotidiano |

**Esta PR será validada por CI no SHA final e links documentais.** Não executar instaladores, import com API, teste Live, desktop/microfone ou script que possa mudar dados do proprietário como parte de uma etapa exclusivamente documental.

## 8. Pendências após completar o inventário inicial

1. **Entrada e ambiente:** unificar bootstrap Python GUI/voz/instalação/testes, inclusive fallback e mensagens de erro; adicionar testes sobre a seleção do interpretador.
2. **Instalador de voz:** corrigir política de cache ASR, lógica de remoção/verificação e retorno de erro em PR própria, preservando modelos existentes.
3. **Modelo configurável:** a candidata corrige a divergência `config.py` ↔ `auren.py` ↔ prompt com tests de import em subprocesso; faltam validação real de modelos alternativos na API e revisão antes de integrar, sem mudanças silenciosas de versão/compatibilidade.
4. **Preparação do navegador:** documentar/automatizar verificação ou instalação de Chromium Playwright sob consentimento adequado, sem alegar que `pip install` basta.
5. **Distribuição:** decidir futuramente se deve existir empacotamento portátil, instalador, ambiente isolado e estratégia de atualização/rollback. **Não criar EXE nem serviço automaticamente**.
6. **Recuperação:** revisar backups de dados de memória, caches, configurações pessoais e permissões, sem copiar segredos para Git.
7. **Documentação longitudinal:** após esta etapa, consolidar `AUREN_STATE.md` em **estado atual curto** mais histórico selecionado, preservar evidências de PRs/runs e revisar redundâncias. Isso exige tarefa documental **separada** para não misturar com a etapa 10.

**Conclusão de escopo:** etapas 0–10 do inventário inicial terão documentação estática após integração desta PR. O Auren **não** está “finalizado”, “inteiramente testado” ou “pronto para distribuir” por causa disso.
