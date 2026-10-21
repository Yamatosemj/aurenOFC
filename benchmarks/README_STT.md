# Avaliação STT PT-BR — Etapa 5A

Infraestrutura isolada: não importada pela voz, UI ou Harness. O STT de produção
continua Parakeet. Sem wake word, microfone, instalador, download ou cliente de
API implícito. Nenhuma dependência nova de produção.

## Plano seguro, sem áudio nem modelos

Na raiz do checkout, com Python existente:

```powershell
python -m benchmarks.stt benchmarks/stt_ptbr.json --output ../plan-stt.json
python -m pytest tests/test_stt_benchmark.py -q
```

O plano deixa WER/CER/latência como null. Os 12 roteiros são **textos para futura
coleta**, não gravações nem resultados de reconhecimento. O arquivo de saída
deve ser novo; não se sobrescreve evidência. Não executar exemplos de inferência
abaixo sem autorização posterior para áudio/modelos.

## Corpus posterior autorizado

Manter cópia de trabalho do manifesto fora do checkout. Cada item requer `audio`
relativo à raiz do corpus, `permission: approved`, `source`, `license`, SHA256 e
referência literal revisada. WAV mono PCM16 16 kHz, até 60 s/2 MB. Nenhum áudio é
buscado automaticamente. Arquivos fora da raiz, inclusive symlinks resolvidos,
são recusados. Referências nunca são enviadas como prompt aos reconhecedores.

Cobertura: frases curtas/longas, automação, nomes, números/negação, hesitação,
pausa e ruído branco determinístico 15 dB SNR. Para cada condição ruidosa,
adicionar também versão limpa do mesmo áudio com outro ID, sem noise_snr_db.
Ruído sintético não representa todo ambiente real. Áudio de pausa precisa de
pausa gravada; a referência mantém palavras/hesitações, não marcas de silêncio.
Coletar vários falantes/sotaques e exemplos adicionais antes de escolher.

## Inferência local posterior, somente com cache explicitamente fornecido

```powershell
python -m benchmarks.stt ../corpus/manifest.json --engine faster-whisper --allow-local-audio --audio-root ../corpus --model-dir ../models/whisper-small-ct2 --model-revision REVISAO_IMUTAVEL --threads 4 --repetitions 5 --output ../faster-small.json
python -m benchmarks.stt ../corpus/manifest.json --engine parakeet --allow-local-audio --audio-root ../corpus --model-dir ../models/parakeet --model-revision REVISAO_IMUTAVEL --repetitions 5 --output ../parakeet.json
```

Prover ambiente separado compatível antes de rodar; faster-whisper/CTranslate2
são dependências opcionais ainda **não instaladas nem fixadas nesta etapa**.
Fixar versões e wheels após teste de compatibilidade Python 3.13/Windows. O
benchmark registra versões encontradas; não modifica requirements. faster-whisper
aceita só pasta existente e local_files_only=True, CPU INT8/4 threads/beam 5,
idioma pt, sem VAD extra nem contexto da amostra anterior. Comparar base/small
multilíngues, jamais variantes .en para PT-BR. Consumir o gerador faz parte do
tempo de transcrição. Não extrapolar testes batched para PTT de uma fala.

Parakeet usa onnx_asr com pasta explícita completa (incluindo aliases ONNX já
preparados), injeta o modelo carregado no LocalPortugueseASR existente e preserva
seu ganho/preparo. Não chama o download nem prepara aliases. A revisão informada
é declarada, não atestada: guardar hashes dos pesos e versão do driver/SO junto
da evidência da coleta. Não utilizar cache pessoal nesta etapa.

## Cloud posterior: adaptador preparado, execução pendente

Cloud recebe `client` compatível com `client.audio.transcriptions.create`,
`authorized=True` e `budget_usd` explícitos; não descobre chaves nem cria cliente.
Modelos exatos: Groq whisper-large-v3-turbo e OpenAI gpt-4o-mini-transcribe, WAV,
language=pt/JSON/temperature=0. A CLI não tem opção de API paga.

Após nova autorização, um chamador poderá fornecer cliente com endpoint do
provedor, timeout finito e max_retries=0, e encaminhá-lo a evaluate. Revisar
permissão de upload e quota/custo total das repetições antes disso. A reserva
local usa preços estimados por duração, inclusive mínimo de 10 s da Groq; não é
um limite financeiro rígido da conta. OpenAI cobra por tokens, portanto a taxa
estimada/minuto não garante teto; usar também limite no provedor. Testes atuais
injetam clientes falsos, inclusive falha/recusa/orçamento, sem chamadas reais.

## Métricas e interpretação

- `startup_ms`: imports/carregamento de um motor; executar processo novo por
  motor para comparar inicialização. Cache de disco frio não é garantido.
- Primeira inferência separada de p50/p95 quentes. Repetições não são novos
  falantes. Usar pelo menos cinco e alternar ordem de motores entre processos.
- `prepare_ms`: leitura WAV e ruído; `transcribe_ms`: fronteira do adaptador,
  incluindo conversão, inferência/upload/rede quando houver; `delivery_ms`:
  montagem final do texto. `audio_ready_to_text_ms` soma essas etapas, **sem**
  startup, captura, segmentação PTT e fila. Não chamar isso de ponta a ponta.
- `capture_ms`/`queue_ms` ficam null: medição física e instrumentação de PTT/UI
  são pendentes. Anotar futuramente pressionar/soltar tecla, captura pronta,
  enqueue/dequeue e texto visível para separar esses tempos. A CLI não os simula.
- WER/CER por Levenshtein; agregação micro por contagens, não média das taxas.
  NFC/casefold/pontuação removida; preserva acentos, números, negação e hesitações.
  CER ignora espaços. Referência vazia retorna taxa null e conserva inserções.
  Erro em nome, número ou negação exige revisão por caso, além de WER global.
- Sem amostras: nenhum motor é inicializado. `pending_audio` não é aprovado.
  Qualquer falha de inferência interrompe a execução; não gera agregado verde
  parcial. Medidas com cliente roteirizado devem usar simulated=True.
- RAM/CPU no i5 e tempo de captura/fila ainda precisam de coleta externa
  autorizada; versões, configuração e duração dos clipes ficam no JSON. RTF é
  tempo do adaptador/duração. P95 com corpus pequeno é apenas descritivo.

Fontes/preços, diagnóstico, recomendação e resultados: [relatório](../RELATORIO_ETAPA5A.md).
