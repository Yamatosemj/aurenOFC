# Auren — Etapa 5A: avaliação e preparação de STT

Data: 2026-10-21. **Infraestrutura preparada; nenhum mecanismo vencedor medido.**
Base: PR #178, `8f3b757de0b1f3962576df1091c7f4ae232a5adb`, conferida no GitHub.
Worktree isolado `etapa5a/repo`, branch `avaliacao/etapa5a-stt-20261021`.
Main remota conferida em `70b040d6191237e2f0a291a14b8ea8fb4b78a09d`.

## 1. Diagnóstico do STT atual

Lidos AGENTS, estado, README/inventário, documentação de voz/interface, código
V48 (voice/main.py, input.py, segmentation.py, stt.py), dependências e relatórios
de latência/usabilidade. V48 é histórico do código de voz; config continua V47.

O STT atual **não é faster-whisper**: LocalPortugueseASR usa Parakeet TDT 0.6B
pt-BR TAGARELA ONNX INT8 em CPU. LocalWhisper é alias de compatibilidade. Não
foi alterado. Não há wake word: PTT usa Ctrl direito + Shift direito.

| Etapa | Evidência estática e impacto possível |
| --- | --- |
| Captura | Stream/dispositivo/taxa são preparados por captura. Fallback de taxa/driver pode custar tempo; não foi medido fisicamente. Fala só termina ao soltar a tecla ou atingir limite de 30 s. |
| Borda PTT | Polling 20 ms, debounce 60 ms, pré-roll 180 ms e pós-roll 120 ms configurados. Pós-roll acrescenta espera após soltar; pré-roll é histórico de áudio, não deve ser somado automaticamente como atraso. São parâmetros, não latências medidas. |
| Segmentação | Concatenação, sanitização, mono, WebRTC VAD; fallback por energia se indisponível/inválido. Padding 80/120 ms recorta o áudio; não equivale a outra espera de 120 ms. Ruído e corte de sílaba podem reduzir precisão antes do modelo. |
| Fila | Áudio até dois itens, texto até 16. Loop serial executa Harness/TTS; entrada pode esperar processamento anterior. get de áudio tem timeout de 50 ms; não é atraso obrigatório por mensagem. |
| Inicialização | Warm-up em thread inicia antes da primeira fala; lock de inferência faz uma fala que chegou cedo esperar o carregamento. Cache ausente/incompleto pode baixar modelo; cache identifica repo/revision, mas default main não é revisão imutável. |
| Preparo/inferência | Resample para 16 kHz, ganho controlado, recognize e normalização do texto. Esses custos hoje ficam dentro de transcrever, sem spans separados. |
| Entrega | Texto só é impresso/enviado ao Harness depois da transcrição inteira. UI Chrome/Tk ainda é textual, sem ligação PTT integrada neste checkout. |

“Latência ASR” mede chamada completa a transcrever, inclusive espera no lock ou
carregamento tardio, mas exclui captura/VAD/fila. “Texto → voz” começa depois do
STT e inclui Harness/revisores/TTS. Não se pode atribuir a lentidão ao modelo.
Relatórios anteriores medem orquestração/interface e cenários de automação,
sem benchmark auditável de reconhecimento de fala em PT-BR. Não se reutilizam
os tempos de saudação/maximização como tempos STT.

## 2. Comparativo técnico e fontes atuais

Fontes oficiais consultadas em 2026-10-21; preços sujeitos a alteração. Todas as
afirmações de qualidade/velocidade abaixo são hipóteses de avaliação, não WER
ou latência medida no Auren.

| Candidato | Precisão esperada e compatibilidade | Recursos/dependências | Latência e custo |
| --- | --- | --- | --- |
| Parakeet atual | Especialização PT-BR justifica baseline obrigatório; nomes, ruído e sotaques sem evidência própria. | onnx-asr/ONNX CPU já previstos em requirements-voice; RAM efetiva não medida. | Modelo residente evita carga por fala; API US$ 0, energia/hardware não inclusos. |
| faster-whisper local | Comparar base e small multilíngues; tamanho maior pode melhorar reconhecimento, sem garantia para comandos/nomes. PT explícito, CPU INT8. | CTranslate2, PyAV, tokenizer/HF e NumPy opcionais; wheel Windows/Python 3.13 precisa ensaio. Nenhuma instalação feita. | Depende de CPU/threads/beam. O projeto publica small INT8 usando cerca de 1,48 GB num i7-12700K/8 threads; isso não prevê o i5. API US$ 0. [Projeto](https://github.com/SYSTRAN/faster-whisper). |
| Groq Whisper Large V3 Turbo | Whisper multilíngue; candidato principal de nuvem por custo. Precisão de comandos brasileiros ainda pendente. | Cliente compatível com API OpenAI; sem pesos locais, CPU/RAM principalmente áudio/cliente, sem medição. Upload/rede necessários. | US$ 0,04/h de áudio, mínimo faturado 10 s por chamada. Rede/fila/serviço dominam o tempo percebido em falas curtas; medir no Auren. [Groq STT](https://console.groq.com/docs/speech-to-text). |
| OpenAI GPT-4o Mini Transcribe | Candidato de qualidade para comparação; não assumir superioridade em nomes ou fala hesitante sem corpus próprio. | SDK já previsto no projeto, endpoint de transcrição; sem modelo local. Adaptador usa modelo solicitado, sem substituir por outro. | Estimativa oficial US$ 0,003/min; faturamento por tokens pode variar. Inicialização do cliente e RTT não foram medidos. [Modelo](https://developers.openai.com/api/docs/models/gpt-4o-mini-transcribe), [preços](https://developers.openai.com/api/docs/pricing), [contrato](https://developers.openai.com/api/reference/resources/audio/subresources/transcriptions/methods/create). |
| whisper.cpp/OpenVINO | Alternativa local pertinente se CPU não satisfizer e houver benefício Intel demonstrável. Mesmo corpus necessário. | Binário/build e pesos próprios; mais manutenção. Não foi adicionado adaptador nesta etapa. | Tem suporte OpenVINO/Windows; potencial de aceleração Intel exige teste, sem garantia para Iris Xe. [Projeto](https://github.com/ggml-org/whisper.cpp). |

No i5-1135G7/Iris Xe/24 GB informado, começar CPU INT8 com quatro threads e uma
fala por vez. RAM total não parece impeditivo para small, mas uso conjunto de
Chrome, LLM/TTS e pressão térmica precisa ser medido; não foi inspecionado o PC.
O backend GPU de CTranslate2 pré-compilado é NVIDIA, portanto **não planejar
CUDA na Iris Xe**. [Hardware oficial](https://opennmt.net/CTranslate2/hardware_support.html).

Não usar throughput de lotes, WER agregado estrangeiro ou benchmarks de GPUs
como evidência de resposta rápida/precisa no notebook. Foram omitidos rankings
numéricos de precisão de terceiros justamente por não representarem o corpus.

## 3. Infraestrutura e resultados realmente medidos

Novos arquivos: benchmarks/stt.py, stt_ptbr.json, README_STT.md e
tests/test_stt_benchmark.py. Adaptadores Parakeet/faster-whisper de cache explícito,
e Groq/OpenAI com cliente injetado. Nenhum import no runtime existente.

12 roteiros PT-BR: curto/longo, automação, nomes, números, negação,
esclarecimento, pausas, hesitações e ruído determinístico 15 dB SNR. **São
referências textuais; nenhuma gravação foi fabricada.** Não foram encontrados
WAV/FLAC/MP3/OGG versionados com referência utilizável. Arquivos pessoais e
caches pessoais não foram procurados. Sem corpus aprovado, todos os ensaios
reais ficam pendentes, com WER/CER e latência null em plan-stt.json externo.

| Evidência | Resultado |
| --- | --- |
| Testes offline da infraestrutura | 19 testes da infraestrutura aprovados na bateria final; 215 aprovados no total local, zero falhas/ignorados e blocked=[]. Inclui continuidade #178, evidência, buffer/shutdown/estado de voz, confirmação, UI e caminho único. JUnit externo em runs/offline-final3/pytest.xml. |
| Qualidade STT nos quatro motores | Pendente: zero áudios de fala transcritos. |
| Inicialização/inferência/RAM reais no i5 | Pendente: não carregamos pesos, nem medimos uso pessoal. |
| Nuvem | Zero requisições reais; só clientes simulados. |
| Custos incorridos | US$ 0,00; nenhuma instalação/download de modelo ou captura. |

Validação local final usou runner externo run_tests.py e cópia das guardas anteriores, com rede/subprocessos/desktop bloqueados e perfis descartáveis. A primeira tentativa de runner foi bloqueada ao abrir o destino de log padrão do pytest (`\\.\nul`); configurado log explícito dentro da área descartável e repetido, sem relaxar guardas. Ensaios anteriores preservados. O plano padrão foi executado e gerou 12 pendências, sem ler áudio.

O ambiente Python 3.13 do venv anterior tem pytest/OpenAI, mas não NumPy,
onnx-asr ou faster-whisper. Nenhuma dependência foi instalada para preencher a
lacuna. Testes próprios usam biblioteca padrão, mocks explícitos e tons gerados
descartáveis; estes não são evidência de reconhecimento ou acurácia real.

O benchmark mede inicialização, primeira inferência, preparo, transcrição,
montagem do texto, p50/p95 quentes, RTF e WER/CER micro. Registra versões e
configuração/revisão declarada. Captura/fila ficam null; protocolo de medição
PTT está no README. WAV mono/16 kHz/PCM16 e SHA256, proveniência/permissão e raiz
explícita são exigidos para inferência futura. Cloud não é executável pela CLI.
Não há download nem acesso automático a credenciais. Instruções reproduzíveis
em [benchmarks/README_STT.md](benchmarks/README_STT.md).

## 4. Estimativa mensal de custo

Somente STT, 30 dias/mês, sem impostos/câmbio, sem free tier presumido e sem
retries. Duas distribuições: requisições de 10 s ou mais e PTT de 3 s em média.
Para Groq: soma(max(duração,10))*0,04/3600. Mini: minutos*0,003, estimativa.

| Uso de áudio/dia | Minutos/mês | Local API | Groq ≥10 s | Groq 3 s | OpenAI Mini |
| --- | ---: | ---: | ---: | ---: | ---: |
| 5 min | 150 | US$ 0 | US$ 0,10 | US$ 0,33 | US$ 0,45 |
| 15 min | 450 | US$ 0 | US$ 0,30 | US$ 1,00 | US$ 1,35 |
| 30 min | 900 | US$ 0 | US$ 0,60 | US$ 2,00 | US$ 2,70 |
| 60 min | 1800 | US$ 0 | US$ 1,20 | US$ 4,00 | US$ 5,40 |

Comandos de 1 s deixam o mínimo da Groq mais relevante: 900 minutos custariam
cerca de US$ 6,00. Repetições de benchmark e confirmações de voz também contam.
Não agrupar comandos esperando completar 10 s para economizar: isso prejudica
PTT e separação de tarefas. Esses valores são cálculos dos preços acima, não
faturas medidas nem limites garantidos do adaptador.

Se US$ 5 for a meta mensal de **todo** o Auren, reservar antes o custo do modelo
principal e revisores. Com 900 min de PTT/3 s, Groq deixa US$ 3,00 e Mini US$
2,30 dessa meta; local deixa US$ 5,00, excluída energia. LLM/revisores dependem
de chamadas/tokens e não há uso mensal representativo nesta etapa para garanti-los.

Teto geral: `câmbio efetivo*(STT+LLM+TTS)+encargos ≤ R$100`. Não é orçamento
exclusivo de STT. Sensibilidade ilustrativa, sem alegar cotação atual: US$ 5
equivalem a R$25/30/35 com câmbio de R$5/6/7 por dólar, antes de taxas. Medir
consumo real e configurar limites de conta antes de prometer enquadramento.

## 5. Limitações e riscos

Sem áudio aprovado, qualidade/latência reais permanecem desconhecidas. Corpus
planejado pequeno, precisa de vários falantes/sotaques, referência humana e
pares limpo/ruído. Ruído branco não representa teclado, TV ou eco. Erros de
negação/números/nomes precisam avaliação por caso, não apenas WER global.
Normalização mantém esses elementos; transcrição nunca é autorização de tool.

PTT físico, áudio cortado, fila, warm-up concorrente, RAM/CPU/temperatura e
entrega ao usuário precisam coleta posterior. Startup não é cache de disco
frio garantido. Modelo/revisão precisam hashes externos; SDK/cliente e timeout
cloud ainda dependem de autorização e ambiente posterior. O budget estimado
do adaptador não substitui teto financeiro do serviço nem tratamento de falhas
para uso cotidiano. Privacidade muda ao enviar áudio à nuvem; upload só pode
ocorrer com permissão específica para as amostras.

## 6. Melhor solução recomendada para o Auren

**Manter Parakeet e PTT atuais enquanto se mede.** Não há vencedor certificado.
Para próxima comparação, priorizar Parakeet vs faster-whisper small/base INT8
como locais, Groq Turbo como primeira hipótese econômica de nuvem e Mini
Transcribe como controle de qualidade. Se Groq demonstrar menor latência e
erros aceitáveis, é o candidato preferencial para nuvem; isso é uma prioridade
de avaliação, não decisão de substituição. Uso offline/privacidade favorece
local, condicionado ao desempenho medido. Não criar fallback automático nem
retransmitir áudio entre provedores nesta etapa.

## 7. Próximo passo para integrar o mecanismo vencedor

Somente após nova instrução: aprovar corpus não pessoal e provisionamento
isolado, fixar pesos/wheels e eventualmente autorizar pequeno orçamento de
comparação cloud. Medir baseline e candidatos no mesmo áudio, processo novo
por motor, primeira chamada separada, cinco repetições e ordem alternada.
Registrar p50/p95 após soltar PTT e tempo até texto, WER/CER por categoria,
nomes/números/negação, recursos e custo com distribuição real de durações.
Meta de engenharia sugerida para discussão: p95 de até 1 s após áudio pronto
em comandos curtos, sem piorar erros críticos; não é SLA já obtido.

Só então propor integração mínima com o contrato transcrever/precarregar e
testar confirmação, cancelamento, shutdown e continuidade #178. Router,
Dispatcher e PermissionManager permanecem donos do caminho de ações.
**Etapa 5B não iniciada. Sem merge, main ou instalação pessoal alterada.**
