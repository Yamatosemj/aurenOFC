# Notas de passagem — Auren Voice/STT V4

Data: 2026-10-08
Branch: `feat/tarefa-1-voice-stt-v48`
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


## Tarefa 6 — barge-in Kokoro

- Saida TTS usa blocos de aproximadamente 50 ms em cada chamada a write.
- Checa cancelamento entre blocos e aborta o stream quando disponivel; sem abort, usa stop.
- Reproducao normal mantem stop, close, callback unico e uma chamada ao modelo.
- Locks sao liberados mesmo quando um bloco de escrita falha.
- Simulacao anterior demonstrou write bloqueante para chunk completo de 4 segundos.
- Testes novos cobrem cancelamento, fallback, ordem das amostras e erros.
- Validacao funcional no Windows, relatada pelo usuario: ESC cortou imediatamente; PTT cortou imediatamente; reproducao normal sem falhas; nenhuma observacao adicional.
- Nao houve cronometro ou medida instrumental em milissegundos; comportamento com outros dispositivos/drivers continua nao verificado.
- CI do commit `99452aeb`: pytest completo Linux 462 passed/6 skipped; focado Linux 79 passed/6 skipped; focado Windows 85 passed.


## Tarefa 7 — pré-roll retido por amostra

- O callback do PortAudio descarta a quantidade exata de amostras mais antigas, preservando o fim do chunk limítrofe com slicing. O deque continua compatível com NumPy `(N,1)` e listas simples.
- A janela mantém o limite de 180 ms (2880 amostras a 16 kHz) e os dados mais recentes mesmo quando um callback entrega 3200 ou 8000 amostras de uma vez.
- A gravação continua começando pelo pré-roll antes dos novos frames. `definir_saida_ativa(True)` e `limpar_pre_roll()` continuam limpando o deque e o contador.
- Regressões adicionadas a `tests/test_voice.py` para blocos de 480, 1600, 3200 e 8000 amostras, NumPy (N,1) e listas, ordem de gravação e supressão durante saída de TTS.
- Validação RED na branch temporária: focado Linux 8 failed/81 passed/6 skipped; focado Windows 8 failed/87 passed; suíte completa Linux 8 failed/464 passed/6 skipped.
- Validação GREEN na branch temporária com a correção: focado Linux 89 passed/6 skipped; focado Windows 95 passed; suíte completa Linux 472 passed/6 skipped. PR temporária #97 apenas para executar o CI; não deve ser mesclada.
- Nenhum parâmetro de latência, tamanho de bloco do PortAudio, pós-roll ou debounce foi alterado.
- Teste de microfone real no Windows e avaliação de latência/overflow permanecem pendentes.
