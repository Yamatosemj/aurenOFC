# Notas de passagem — Auren Voice/STT V4

Data: 2026-10-08
Branch: `fix/tarefa-4-voice-confirmation-queue`
Tarefa: Sistema de voz e STT

## O que foi feito

- captura PTT com stream aberto localmente, pré-roll curto e pós-roll
- debounce de Ctrl+Shift+Space para evitar acionamento acidental
- segmentação local com WebRTC VAD, com fallback por energia
- descarte de silêncio quase puro antes do ASR
- resolução do microfone por nome e fallback para o dispositivo padrão
- tentativa da taxa preferida e fallback para a taxa nativa do dispositivo
- normalização do áudio para mono, valores finitos e 16 kHz antes do Parakeet
- acesso serializado ao modelo STT
- falhas de captura/STT não encerram mais a sessão de voz
- TTS fica fora do pré-roll para a próxima fala
- voz continua usando o mesmo AurenHarness da entrada textual
- testes da camada de voz ampliados
- instalador preserva o cache local do modelo
- wake word e Echo Guard não foram implementados

## Referência técnica

O Mark-LV foi usado como referência para decisões de baixo nível como VAD, tratamento das bordas da fala, debounce de PTT e resolução resiliente de dispositivo. Nenhum código ou comentário do projeto foi copiado.

## Arquivos alterados/criados

- `voice/segmentation.py` — novo segmentador de fala
- `voice/input.py` — captura PTT V4
- `voice/stt.py` — preparação/resampling e resiliência do ASR
- `voice/confirmation.py` — evita que o prompt de confirmação entre no pré-roll
- `voice/main.py` — integração e recuperação de erros
- `voice/__init__.py` — exportações
- `requirements-voice.txt` — WebRTC VAD
- `INSTALAR_VOZ.bat` — preservação do cache
- `AUREN_VOZ.bat` — identificação V4
- `config.py` e `auren.py` — versão V48
- `tests/test_voice.py` — cobertura nova
- `.github/workflows/auren-visual-interaction.yml` — voz incluída no CI
- `README.md` — documentação V4
- `AUREN_STATE.md` — estado oficial
- `docs/NOTAS_DE_PASSAGEM.md` — esta passagem

## Validação

A validação local focada passou com **6 testes** cobrindo resampling 48→16 kHz, rejeição de audio curto, VAD com padding, silencio, resolução de microfone e confirmação por voz. O CI V48 ainda não reportou status para o head atual. O teste final de qualidade depende de um Windows com microfone real, porque latência percebida, driver, ruído e qualidade do PT-BR não podem ser validados apenas por testes unitários.

## Próximo passo

Executar a bateria de voz no Windows real e medir exemplos curtos, comandos naturais, fala lenta/rápida, pausas, ruído e troca/ausência do microfone. Só depois disso decidir ajustes finos dos limiares de VAD.


## Correção de segurança nesta passagem

- resultados OK de `ler_pagina`, `ler_arquivo` e `obter_contexto_navegador` passam a registrar a fonte não confiável no `PermissionManager` mesmo quando a própria ferramenta já devolve `conteudo_nao_confiavel=True`
- a marcação existente de `ler_pagina` foi preservada
- regressões adicionadas pelo fluxo `executar_ferramenta` cobrem leitura real de arquivo, contexto de navegador, leitura de página, ausência de leitura anterior e limpeza por `iniciar_tarefa()`
- nenhuma nova ferramenta foi classificada como não confiável e nenhuma capacidade/permissão foi afrouxada


## Correção da configuração do modelo — Tarefa 2

- `auren.MODEL` acompanha o valor efetivo de `config.MODEL`, incluindo quando `AUREN_MODEL` define outro modelo
- o literal padrão `gpt-5.6-luna` permanece reconhecível pelo leitor regex de `testes_auren_live.py`
- a verificação de coerência de `AUREN_VERSION`, `CACHE_KEY` e `ARCHITECTURE_NAME` foi mantida
- `tests/test_model_config.py` cobre os imports em subprocesso, a preservação do literal de compatibilidade e o restauro do módulo `config` após testes que alteram o ambiente


## Tarefa 3 — fallback da taxa nativa do microfone

- `voice/input.py` agora retorna `default_samplerate` como taxa nativa, sem substituí-la pela taxa preferida configurada
- `_abrir_stream()` tenta taxas únicas na ordem: preferida, nativa, 48 kHz e 44,1 kHz; para na primeira abertura bem-sucedida
- se todas falharem, o erro mantém os detalhes por taxa tentada
- o fallback de dispositivo padrão permanece preservado quando o nome selecionado não existe ou o stream selecionado falha
- a taxa do stream que abriu continua fluindo para segmentação e `CapturedAudio.sample_rate`; o STT segue normalizando para 16 kHz
- testes determinísticos novos usam sounddevice falso para cobrir rejeição da taxa preferida, sucesso imediato, microfone configurado inexistente e falha de todas as taxas
- nenhuma alteração em `voice/segmentation.py`, `voice/stt.py`, `voice/tts.py`, pré-roll, pós-roll ou debounce
- CI de validação concluído: suíte completa com 462 passed e 6 skipped; testes focados V48 com 83 passed e 6 skipped no Linux e 89 passed no Windows. O teste local do usuário no Windows concluiu `tests/test_voice.py` com 18 passed em 0,34 s. No teste físico seguinte, `Microfone (Realtek(R) Audio)` abriu a 16.000 Hz; houve captura de 1,64 s, transcrição pelo ASR em 0,295 s e resposta por voz. Um aviso de input overflow apareceu durante a captura, mas não impediu essa execução; acompanhar em testes posteriores. O fallback para outras taxas continua validado pelos testes com sounddevice falso, pois o dispositivo real aceitou 16 kHz.


## Tarefa 4 — confirmação por voz e fila de áudio

- `normalizar_resposta_falada()` é o helper único usado pela confirmação e pelos comandos de saída do `voice/main.py`; remove acentos e pontuação, converte para minúsculas e colapsa espaços.
- A confirmação só aceita `sim`, `s`, `yes`, `y`, `pode`, `pode sim`, `sim pode`, `confirmo` ou `autorizo`; palavras de negação (`nao`, `nunca`, `cancela`, `para`) prevalecem antes da lista afirmativa. Respostas ambíguas negam.
- A fila compartilhada é esvaziada com `get_nowait()` em loop antes do prompt. Não há limpeza após o TTS, para preservar uma resposta iniciada durante o prompt.
- Só um item do formato `("audio", CapturedAudio)` é enviado ao ASR; erros de captura, itens crus, payloads vazios ou de outro tipo negam.
- `core/confirmation.py` (canal textual), timeout e Echo Guard permanecem inalterados.
- Testes de pontuação, lista fechada, prioridade da negação, fila antiga, fala nova durante o prompt, payload inválido e comandos de saída estão adicionados. CI validado no commit de código `304b026`: suíte completa Linux com 499 passed/6 skipped; testes focados Linux com 124 passed/6 skipped e Windows com 130 passed. O teste local Windows desta tarefa ainda não foi executado pelo usuário.


## Tarefa 5 — áudio sem fala não chega ao ASR

- Decisão válida de ausência de fala pelo WebRTC é definitiva: não usamos energia para contrariá-la.
- Energia atua exclusivamente na falta/erro do WebRTC; sem quadros de fala suficientes, `segment()` retorna `None`.
- O caminho existente em `voice/input.py` já descarta `None` e avisa o usuário, de forma que não foi alterado. `voice/main.py`, `voice/stt.py`, `voice/tts.py` e `voice/confirmation.py` seguem sem mudanças nesta tarefa.
- O detector de energia mantém os mesmos parâmetros: percentil 20 para piso de ruído, energia de quadro ≥2× o piso (ou mínimo `silence_rms`) e pico ≥0,35× `silence_peak`. São critérios heurísticos para preservar fala baixa; não distinguem com garantia todos os tipos de ruído variável.
- Novas regressões com ruído controlado, WebRTC falso/erro, tom modulado e fala baixa. Ajustes finos dependem de validação com microfone real no Windows.
