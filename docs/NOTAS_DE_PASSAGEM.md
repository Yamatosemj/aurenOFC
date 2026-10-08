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
