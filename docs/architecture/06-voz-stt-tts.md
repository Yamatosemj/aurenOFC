# Arquitetura 06 — Voz, PTT, VAD, STT e TTS

> **Etapa 6 — auditoria estática** da `main` em `7a13c412463ad55ef7fe5562ad2e757feb2cebde` (2026-10-10). A candidata de voz V48 está integrada no repositório (PR #119), mas a versão técnica do programa em [config.py](../../config.py) continua **V47**. Os componentes internos que se intitulam *Voice Engine V4* e os scripts que ainda exibem *V3* não são, por si, releases separadas. **Não houve teste físico de microfone, saída de áudio, qualidade de reconhecimento ou latência nesta auditoria.**
>
> Este documento cobre a **entrada por voz**, a transcrição local e a resposta falada. As ferramentas acionadas após a transcrição pertencem ao mesmo [Harness](01-nucleo.md) e à mesma [política de ferramentas](02-roteamento-seguranca.md). Não transformar decisões de arquitetura de áudio em caminhos paralelos de execução.

## 1. Mapa de implementação e dependências

| Fonte | Responsabilidade |
| --- | --- |
| [`voice/main.py`](../../voice/main.py) | Entrada do modo voz, três threads de suporte (texto, PTT e aquecimento STT), filas, ciclo de transcrição → Harness → fala, interrupção da saída e encerramento |
| [`voice/input.py`](../../voice/input.py) | Captura PTT por `sounddevice` e tecla global `keyboard`, dispositivo, taxa amostral, pré/pós-roll e envelope `CapturedAudio` |
| [`voice/segmentation.py`](../../voice/segmentation.py) | Decisão local de presença de fala via WebRTC VAD, fallback de energia e recorte com padding |
| [`voice/stt.py`](../../voice/stt.py) | ASR Parakeet TDT pt-BR (ONNX INT8), preparação 16 kHz, ganho controlado, download/carregamento e inferência |
| [`voice/tts.py`](../../voice/tts.py) | Kokoro ONNX, download/carregamento dos modelos, chunks assíncronos e reprodução pelo dispositivo de saída |
| [`voice/speech_response.py`](../../voice/speech_response.py) | Formatação de respostas técnicas em frases curtas para fala |
| [`voice/confirmation.py`](../../voice/confirmation.py) | Canal de autorização por fala: prompt TTS, resposta por áudio/STT, allowlist afirmativa e negação padrão |
| [`voice/list_devices.py`](../../voice/list_devices.py) | Diagnóstico/listagem de microfones e auxílio à configuração |
| [`agent/ari_native/audio_manager.py`](../../agent/ari_native/audio_manager.py) | Locks independentes de sessão de entrada e saída; **não** é mixer, cancelador de eco ou intertravamento bidirecional |
| [`auren.py`](../../auren.py) | Fábrica compartilhada `criar_harness(confirmation_channel=...)` e caminho de ferramentas normal |
| [`scripts/iniciar/AUREN_VOZ.bat`](../../scripts/iniciar/AUREN_VOZ.bat) | Inicia `voice/main.py` com Python da `.venv` ou `py -3` |
| [`scripts/instalar/INSTALAR_VOZ.bat`](../../scripts/instalar/INSTALAR_VOZ.bat) | Instala dependências específicas de voz e trata o diretório de cache ASR |
| [`scripts/diagnosticos/AUREN_LISTAR_MICROFONES.bat`](../../scripts/diagnosticos/AUREN_LISTAR_MICROFONES.bat) | Executa a listagem de dispositivos |
| [`scripts/testar/TESTAR_VOZ.bat`](../../scripts/testar/TESTAR_VOZ.bat) | Executa `pytest -q tests/test_voice.py`, **não** testes Live de hardware |

[`requirements-voice.txt`](../../requirements-voice.txt) fixa `onnx-asr[cpu,hub]==0.12.0`, `kokoro-onnx==0.6.1`, `sounddevice==0.5.6`, `soundfile==0.13.1`, `keyboard==0.13.5`, `numpy==2.5.3` e `webrtcvad-wheels==2.0.14.post1`. As dependências são separadas do `requirements.txt` geral; essa separação evita importar equipamentos e modelos de áudio em tarefas de texto normais.

## 2. Fluxo real: o que acontece quando se fala

```text
AUREN_VOZ.bat → voice/main.py
 ├─ leitor texto (thread daemon) ───────────────┐
 ├─ captura PTT (thread daemon)                  │
 │   teclado global + microfone sounddevice     │
 │   pré/pós-roll → WebRTC VAD ou energy         │
 │   CapturedAudio na fila de áudio             │
 └─ warm-up do Parakeet (thread daemon)          │
        ↓                                        │
 main: CapturedAudio → Parakeet local (texto) ←─┘
        ↓
 auren.criar_harness(VoiceConfirmationChannel)
        ↓
 Harness normal → Router → Dispatcher → contrato → permissão → ToolResult
        ↓
 SpeechResponseFormatter → Kokoro local → OutputStream
        ↓
 volta a aguardar entrada
```

O ciclo **não** é um stream full-duplex de fala com o modelo: uma fala PTT é capturada como trecho, transcrita localmente e enviada **como texto** ao Harness. O Harness pode usar o provedor de modelo configurado e suas ferramentas; *local-first para STT/TTS* **não** significa que todas as respostas ou ferramentas funcionem offline. Não há hotword/wake word no caminho ativo: [`experimental/wake_word.py`](../../experimental/wake_word.py) é experimental.

`voice/main.py` tem **filas separadas para texto e áudio**. O leitor de texto envia `("texto", mensagem)`; a captura envia `("audio", CapturedAudio | None)` ou `("erro_captura", exceção)` e tenta novamente após falha. O loop principal prioriza verificar a fila de texto, depois a de áudio; só processa uma tarefa de Harness de cada vez. O pré-carregamento ASR usa thread, mas a inferência é protegida por lock.

**Limite:** o processo encerra por ESC, comando de saída exato (como `sair` / `encerrar` / `fechar o auren`) ou EOF da entrada de texto. Threads são daemon e `finally` sinaliza `stop_event` e fecha navegador; não há garantia de interrupção instantânea de toda chamada externa ou de desligamento ordenado de um stream bloqueado.

## 3. PTT e captura de microfone

[`PushToTalkRecorder`](../../voice/input.py) usa por padrão **`right ctrl+right shift`** (Ctrl direito + Shift direito, juntos); ESC encerra. O PTT é observado por polling a cada **20 ms** com debounce padrão de **60 ms**. Pressionamento inicia captura e soltar termina; limite de fala **30 s** com espera de liberação da hotkey. Configuração: mono, `float32`, duração mínima de áudio **100 ms**, `pre_roll_seconds=0.18`, `post_roll_seconds=0.12`.

O `InputStream` é aberto **antes** de detectar a hotkey. Enquanto aguarda, um callback guarda somente janela curta de pré-roll em **RAM**; ao pressionar, transfere esse pré-roll para os frames capturados. Ao soltar, retém pós-roll e fecha o stream antes de segmentar. Durante o TTS, `definir_saida_ativa(True)` impede o pré-roll de registrar a voz da própria saída, mas não é cancelamento acústico de eco e **não** bloqueia deliberadamente uma captura que já esteja gravando.

A captura **prefere 16 kHz**, mas tenta também taxa nativa, **48 kHz** e **44,1 kHz** (sem duplicatas); se a seleção de microfone falha, tenta o dispositivo padrão. A variável `AUREN_MIC_DEVICE` aceita nome ou índice: nome é pesquisado novamente ao abrir (igualdade ou correspondência parcial única), índice pode ficar obsoleto quando dispositivos mudam. O stream informa a **taxa efetivamente aberta** no `CapturedAudio`; não declarar que o microfone necessariamente captura em 16 kHz.

**Limites físicos:** suporte à combinação de teclas, interferência de outro aplicativo, permissões do Windows, driver, microfone Bluetooth, ruído, overflow, latência de PortAudio, conflitos de dispositivo e duração de stream precisam ser verificados no hardware. `input_session` serializa capturas de entrada, mas saída tem lock diferente.

## 4. Segmentação e prevenção de áudio sem fala

[`VoiceActivitySegmenter`](../../voice/segmentation.py) avalia a captura **antes** de chamar o ASR. Parâmetros-base: quadros de **20 ms**, modo WebRTC **1**, taxa de decisão **16 kHz**, fala mínima **80 ms**, padding do recorte **80 ms antes** e **120 ms depois**. O recorder sobrescreve a duração mínima de fala para faixa aproximada de 60 a 120 ms, conforme `AudioCaptureConfig`.

- WebRTC VAD é carregado quando disponível, com conversão para PCM16 e normalização moderada **somente para decidir a fala**; decisão válida `sem fala` não ativa o fallback.
- Se WebRTC está ausente, falha ou não produz quadros válidos, entra detector **por energia**. Ele compara RMS de quadros com piso de ruído (percentil 20, razão mínima 2), pico e limiares configurados.
- Se não existem quadros ativos suficientes, `segment` devolve `None` e a gravação **não** é enviada ao ASR; se há fala, retorna áudio original recortado com padding e `vad_backend`.

Esse mecanismo reduz envios de silêncio; **não garante** qualidade de corte de sílabas, robustez a ruído variável ou ausência de falsos positivos/negativos. O fallback simples não é equivalente ao WebRTC em precisão.

## 5. STT local: Parakeet e preparação

[`LocalPortugueseASR`](../../voice/stt.py) usa por padrão o repositório `calneymgp/parakeet-tdt-0.6b-v3-ptBR-TAGARELA-onnx-int8` (pode mudar via `AUREN_ASR_MODEL`) e cache em `data/voice/asr/parakeet-tdt-0.6b-v3-ptBR-TAGARELA-onnx-int8/`. Se faltam arquivos esperados, `huggingface_hub.snapshot_download` busca o snapshot; cria aliases para nomes ONNX compatíveis e carrega `onnx_asr.load_model("nemo-conformer-tdt", path=...)`.

A entrada pode chegar em qualquer taxa suportada pela captura; o ASR normaliza para **16 kHz** por média de blocos em reduções inteiras ou interpolação linear, normaliza nível de fala baixo sem clip intencional e não chama inferência quando o áudio tem menos de **80 ms**. A propriedade `runtime` reporta `onnxruntime-cpu`. O warm-up inicia em thread; não confundir estar carregado com estar validado em fala real.

**Limites:** primeiro uso pode consumir tempo e rede para download; desempenho CPU, qualidade de reconhecimento em PT-BR, nomes próprios, sotaques e ruído são desconhecidos nesta auditoria. O snapshot remoto é selecionado por repositório, sem verificação explícita de hash/revisão fixa no módulo; isso é uma **característica de reprodutibilidade e dependência externa**, não prova automática de comprometimento.

## 6. TTS local: Kokoro e interrupção

[`LocalKokoroTTS`](../../voice/tts.py) usa modelo e vozes em `data/voice/tts/kokoro/`, baixados de URLs fixadas no código quando faltam os arquivos. Padrões: voz `pm_alex`, idioma `pt-br`, velocidade **1.05**. Variáveis: `AUREN_TTS_VOICE`, `AUREN_TTS_LANG` e `AUREN_TTS_SPEED`.

`falar` chama uma vez `Kokoro.create_stream(texto, ...)`, consome os chunks assíncronos e abre `sounddevice.OutputStream` **no primeiro chunk não vazio**; `on_audio_start` marca o início da reprodução. Os chunks são escritos na saída; `cancel_event` é consultado **entre chunks** e a saída é fechada em `finally`. O lock do TTS e `output_session` serializam esse uso do modelo/áudio.

[`_falar_interrompivel`](../../voice/main.py) executa TTS em thread e monitora ESC ou a hotkey PTT: sinaliza cancelamento, faz `join`, limpa o pré-roll e pode informar interrupção. Isso **não** promete cancelamento instantâneo se o sintetizador ou `stream.write` estiver bloqueado. O docstring de `_falar_interrompivel` ainda menciona **F8**, mas a implementação ativa consulta a hotkey `right ctrl+right shift`, não F8. É divergência **textual** pendente de correção específica.

As URLs dos arquivos Kokoro e o modelo ASR podem exigir conexão no primeiro uso. Não há validação criptográfica explícita de hash no método de download TTS; o `.part` evita deixar um arquivo final parcial em uma falha comum de download, mas não valida conteúdo/versão.

## 7. Autorização por voz e formato falado

O Harness de voz recebe [`VoiceConfirmationChannel`](../../voice/confirmation.py) em `auren.criar_harness(confirmation_channel=...)`. Portanto, **a autorização continua no PermissionManager**: este componente é apenas um canal de decisão. Ele limpa áudio antigo da fila **antes** do prompt, fala o pedido pelo TTS, aguarda **um envelope de áudio `("audio", CapturedAudio)`** por até **8 s após a fala do prompt** e transcreve localmente. Timeout, erro, item inesperado, ausência de áudio e respostas ambíguas **negam** a ação.

Só aceita respostas normalizadas inteiras na allowlist (como `sim`, `sim pode`, `pode`, `confirmo`, `autorizo` e variantes inglesas); palavras de negação como `nao`, `cancela`, `nunca` e `para` têm precedência. Não é autenticação de identidade pela voz: qualquer áudio reconhecido na janela de confirmação que satisfizer a regra pode autorizar a ação. A fila também transporta erros de captura, tratados como negação.

[`SpeechResponseFormatter`](../../voice/speech_response.py) produz textos curtos com base no snapshot da tarefa e no resultado da última ferramenta (hora, volume, janela, navegação etc.); o fallback corta Markdown e lê no máximo duas frases/650 caracteres. É **formatação de saída**, não um verificador independente de êxito. Mensagens simplificadas como `"YouTube aberto"` não devem ser tratadas como evidência adicional de que o site ou fluxo externo completou.

## 8. Latência, privacidade e estado operacional

O programa registra **latência ASR** (tempo da chamada `stt.transcrever`) e **latência texto → voz** (depois de obter o texto transcrito ou receber a mensagem digitada até o callback do primeiro áudio). A métrica texto → voz inclui processamento do Harness e preparação de TTS até o primeiro chunk tocado, mas **exclui espera PTT, gravação, segmentação e transcrição**; não é latência ponta a ponta desde que o usuário começou a falar. Também não mede qualidade perceptiva ou tempo até terminar a fala.

Áudio bruto é processado localmente no caminho normal STT/TTS, mas o **texto** segue para o Harness e pode chegar ao provedor do modelo. Modelo ASR/TTS pode ser baixado pela rede; scripts e bibliotecas podem gerar dados locais em `data/voice/`. Não prometer ausência absoluta de rede, retenção zero ou confidencialidade integral apenas porque a inferência de áudio é local.

[`INSTALAR_VOZ.bat`](../../scripts/instalar/INSTALAR_VOZ.bat) remove **todo o diretório de cache ASR indicado** quando ele existe, embora a mensagem diga que limpa apenas cache incompleto. Isso pode provocar **download de novo** após reinstalação, independentemente de o cache anterior estar completo. **Registrado como comportamento de script a verificar/corrigir em tarefa própria; nenhuma mudança de código nesta PR.**

A interface [Tkinter](../../interface_auren.py) é entrada textual separada; o modo de voz roda pela própria entrada `voice/main.py`. O componente [`core/capability_audio_runtime.py`](../../core/capability_audio_runtime.py) é experimento para **controle do áudio do Windows por intenção**, ativado por flag `AUREN_EXPERIMENT_CAPABILITY_AUDIO`; **não** substitui STT, TTS ou o pipeline PTT.

## 9. Evidências de testes — sem confundir mock e Live

| Fonte | Evidência/limite observado |
| --- | --- |
| [`tests/test_voice.py`](../../tests/test_voice.py) | VAD/nível/recorte, taxas de captura, seleção/fallback de microfone, transcrição/resample e TTS com modelos/streams falsos; principal bateria V4 |
| [`tests/test_voice_v3.py`](../../tests/test_voice_v3.py) | Compatibilidade legada, Kokoro stream/cancelamento/formatter; o teste `hotkey="f8"` **injeta F8 explicitamente**, **não** demonstra que o modo voz usa F8 |
| [`tests/test_confirmation.py`](../../tests/test_confirmation.py) | Canales texto e voz; normalização, respostas permitidas, negação, fila antiga, item inválido e timeout |
| [`tests/test_scripts_layout.py`](../../tests/test_scripts_layout.py) | Scripts localizados/caminhos de entrada; não executa instalação nem microfone |
| [`tests/test_permission_policy.py`](../../tests/test_permission_policy.py) | Classificação/autorização de ferramentas por risco, não prova captura de voz |
| [`tests/test_routing_single_owner.py`](../../tests/test_routing_single_owner.py) | Caminho de execução único do Router/Dispatcher, com simulações |

Esses testes foram **inspecionados no código**. Só relatar aprovação de pytest/CI quando a execução for confirmada no SHA desta PR; aprovação de teste de voz com dispositivo/ASR/saída falsos **não** equivale a verificar `Ctrl direito + Shift direito` no notebook, audio Bluetooth, reconhecimento real, eco e latência. O registro antigo do pytest no Windows pessoal da PR #119 cobre **pytest**, não Live.

## 10. Checklist para manutenção e validação futura

1. Conferir [README](../../README.md), [estado](../../AUREN_STATE.md), [inventário](../INVENTARIO.md), a [Etapa 1](01-nucleo.md) e política de [Etapa 2](02-roteamento-seguranca.md).
2. Rastrear `voice/main.py` → PTT → VAD → `CapturedAudio` → ASR → `auren.criar_harness` → canal de confirmação → formatter → TTS; não criar entrada de ferramentas sem Dispatcher.
3. Distinguir interrupção de áudio de **cancelamento da tarefa do Harness**; verificar locks, filas, cleanup e timeouts ao alterar threads.
4. Validar qualquer alteração do VAD com silêncio, ruído, fala baixa, início/fim de sílabas, taxas 16/44,1/48 kHz; separar testes sintéticos de fala real.
5. Para STT/TTS, medir primeira inicialização (download/carregamento), uso repetido, memória/CPU e reprodução real; conferir licenças e versões dos modelos antes de atualizar.
6. Para confirmação por voz, manter decisão conservadora, negando itens antigos/ambíguos; não tratar fala como biometria.
7. Caso autorizado pelo proprietário, executar teste físico pequeno **separadamente**: hotkey/PTT, microfone selecionado, gravação, transcrição PT-BR, TTS, interrupção e latência completa. Registrar ambiente, hardware, logs sem segredos e falhas observadas; **não** iniciar Live nem API paga automaticamente.
8. Se um limite justificar correção, abrir PR de runtime/testes própria; atualizar este documento e `AUREN_STATE.md` após validação.

**Próximo subsistema documental:** Etapa 7 — interface desktop e GUI, em PR separada após esta etapa.
