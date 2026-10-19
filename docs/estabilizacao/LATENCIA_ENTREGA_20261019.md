# Entrega — latência e arquitetura do Auren

Base isolada: #166 (`025351c`), descendente das candidatas #161–165, todas
conferidas abertas. Main remota em `70b040d`, sem merge. Instalação histórica
dos logs em `C:/Users/victo/Downloads/AUREN`, `f1ae0e9`, não substituída.
Implementação em `C:/Users/victo/auren-latencia`. Detalhes A–D, causas e
testes intermediários: [LATENCIA_20261019](LATENCIA_20261019.md).

## Gargalos comprovados e alterações

1. Descoberta repetida antes de PATH: resolução de nome `.exe` exato precede
   catálogo/atalhos; fallback preservado. Elimina candidatos `exe.exe`, raízes
   sobrepostas e lookup implícito no cwd/PATHEXT não-exe. Catálogo e busca
   recursiva ambíguos não lançam alvo arbitrário. Permissões inalteradas.
2. Rodadas para redigir conclusão e consultar estado já disponível: três
   operações de janela passam a devolver leitura Win32 posterior ao efeito,
   no mesmo HWND. A mensagem legível serve de candidata à revisão final.
   Essa revisão permanece; pendência volta ao raciocínio. Somente um pedido
   literal de estado de janela pode dispensar a revisão redundante de intenção.
3. Sequências já conhecidas: modelo pode propor lote, revisado integralmente
   e executado em ordem pelo Harness. Cada ação usa Dispatcher/contratos/escopo/
   PermissionManager. Falha interrompe as restantes; cancelamento é consultado
   entre ações. Outputs `sequence_aborted` preservam call_ids sem inventar
   passos executados. Dependências de leitura/descoberta exigem nova decisão.
4. Contexto: a saudação com zero schemas já era correção da #165, reutilizada.
   No mesmo Router, abertura simples agora recebe cinco ferramentas de execução
   e observação. Composição, condição, arquivos e browser mantêm rotas amplas.
   Falha estruturada de contrato pode ampliar o catálogo na rodada seguinte;
   texto de página ou negação não podem acionar essa expansão. Não existe
   segundo Router, ferramenta por aplicativo, resposta fixa ou novo executor.
5. Diagnósticos: spans de contrato, permissão, execução e revisão; duração por
   ferramenta, resumo de chamadas/tempos e uso conhecido de tokens. Revisão
   final preserva códigos seguros antes ocultados. Novos metadados não incluem
   prompts, conteúdo do revisor, alvos ou mensagens arbitrárias de exceção.
   Schema SQLite e interfaces públicas preservados. Falha de instrumentação
   não muda o resultado operacional, inclusive em resposta incompleta/retomada.

## Comparação medida

Histórico ponta a ponta: saudação 14 s; YouTube 60 s; fechar após esclarecer
14 s; abrir Bloco de Notas 47 s; maximizar 10 s. **Não houve nova bateria paga
com o modelo real**, portanto não há novo tempo ponta a ponta comparável.

| Medição | Antes | Depois | Método e limite |
|---|---:|---:|---|
| Descobrir `notepad.exe` | 11.632,530 ms / 8 subprocessos | 1,895 ms / zero | Descoberta real, lançamento interceptado, uma amostra por revisão. Não mede janela pronta. |
| Maximizar, chamadas reservadas | 5: 3 principais + intenção + final | 2: 1 principal + final | Harness/SQLite/Dispatcher/PM e janela reais; modelo/revisores roteirizados. Estado confirmado independentemente por IsZoomed. |
| Maximizar, tempo desse probe local | 299,129 ms | 280,456 ms | Amostras únicas, não significância estatística nem latência de modelo/rede. |
| Schemas em saudação | 49 / 24.185 caracteres | 0 / 2 | Ganho herdado da #165, não nova implementação desta tarefa. |
| Schemas em abertura simples | 15 / 6.490 caracteres | 5 / 1.928 | Ganho desta etapa E sobre #166; JSON de schemas, não tokens ou payload inteiro. |
| Schemas em maximização | 11 / 4.270 | 11 / 4.270 | Capacidade preservada. |
| Schemas em busca browser/YouTube | 18 / 6.550 | 18 / 6.550 | Capacidade preservada; menos rodadas depende da proposta do modelo real. |

O primeiro probe da candidata mediu 254,976 ms antes da guarda de ambiguidade;
não se atribui a diferença à guarda: há disco, agendamento e inicialização.
A redução de cinco para duas chamadas e de subprocessos/schemas é comprovada;
não se converte isso em promessa de segundos com a API.

Live de estado de janela descartável via Dispatcher/PM: maximizar 8,629 ms,
minimizar 5,644 ms, restaurar 15,961 ms; todos corretos após a correção descrita
abaixo. Não equivale a teste do Bloco de Notas pessoal.

Chromium/DOM reais, perfil temporário, requests interceptados: pesquisar,
ler, clicar em vídeo fictício e verificar URL/título passaram, com confirmação
após fonte não confiável. Coleta focada: 21,38 s para o caso, incluindo browser;
não é YouTube público nem medição com modelo real. Fechamento contextual real
não foi repetido; regressões de fechamento/permissão seguem na suíte.

## Testes e regressões

- Instrumentação: suíte offline completa 1.200 aprovados / oito ignorados.
- Descoberta: 57 testes iniciais focados; 43 de descoberta/telemetria/Dispatcher/
  execução única após organizar o benchmark.
- Evidência de janela: 46 testes focados e Live isolado dos três estados.
- Orquestração/browser: 120 focados; 88 de contrato de recuperação após migrar
  fixtures que continuavam um lote falho.
- Contexto: 76 focados. Revisão ampliada passou 1.239/8 ignorados; coleta
  seguinte 1.240/8, antes das duas últimas regressões de ambiguidade.
- JUnit local final: `C:/Users/victo/auren-latencia-evidence/pytest-final.xml`.
  **1.242 aprovados, oito ignorados, zero falhas, 91,32 s**, após os últimos
  controles de ambiguidade. CI no SHA de entrega é registrado na PR.

Problemas encontrados e tratados:

- TEMP padrão em AppData conflita com política de arquivos: usado o executor
  offline existente, sem enfraquecer a política. Remove credenciais e bloqueia
  sockets Python externos; Chromium usa rotas locais interceptadas.
- Benchmark em scripts/ violava teste arquitetural: movido para tests/, sem
  criar exceção para execução de ferramentas fora do Dispatcher em produção.
- SW_RESTORE após maximizar/minimizar voltava ao estado maximizado: detectado
  em Live, corrigido para SW_SHOWNORMAL e testado novamente. O retorno booleano
  de ShowWindow não é tratado como confirmação de sucesso. Referência:
  [Microsoft/ShowWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-showwindow).
- Testes de lote assumiam continuar após falha: mudados para exigir interrupção
  e recuperação somente em nova rodada, mantendo identidade canônica e falhas
  pendentes. Sucesso em outro alvo não apaga falha anterior.
- Rótulo de domínio de abertura: mantido `apps_files` por compatibilidade.
- Nome exato duplicado com AppIDs diferentes e múltiplos títulos de janela:
  agora falham antes de mutação; pontuação diferente não vira alvo literal igual.
- Versão histórica concluía o probe mas prendia handles SQLite na limpeza:
  gc.collect apenas no teste permitiu comparação limpa. A correção de conexões
  da #165 foi reutilizada, não reimplementada nem aplicada à instalação antiga.

## Arquivos modificados

Produção:

- `core/latency.py` (novo), `harness.py`, `harness_intent_guard.py`,
  `harness_tools.py`, `harness_cycle.py`, `harness_round_input.py`.
- `core/harness_state.py`, `harness_completion.py`, `tool_evidence.py` (novo),
  `task_verification.py`, `intent_verification.py`, `router.py`.
- `providers/openai_provider.py`.
- `tools/applications.py`, `dispatcher.py`, `windows_window.py`.

Testes e probes:

- Novos: `tests/test_latency_instrumentation.py`, `test_executable_exact_resolution.py`,
  `test_window_state_evidence.py`, `test_controlled_sequences.py`,
  `test_contextual_tool_budget.py`, `benchmark_abertura.py`,
  `benchmark_tool_context.py`, `live_window_state.py`, `live_latency_harness.py`.
- Atualizados: `tests/test_application_discovery_latency.py`, `test_audit_p1a.py`,
  `test_harness_loop_owner.py`, `test_harness_tools.py`,
  `test_terminal_completion.py`, `test_offline_browser_usability.py`.
- Estado/documentação: `AUREN_STATE.md`, `docs/estabilizacao/LATENCIA_20261019.md`
  e este relatório. Nenhuma dependência, modelo, preço ou política de autorização
  alterados nesta tarefa.

## Orçamento, PRs e limites

**Limite adicional: US$ 0,50. Chamadas pagas nesta tarefa: zero. Consumo adicional
da API: US$ 0.** Não é estimativa do custo do Codex.

PRs draft empilhadas, sem merge:

- [A #167 — instrumentação](https://github.com/Yamatosemj/aurenOFC/pull/167), base #166.
- [B #168 — executáveis](https://github.com/Yamatosemj/aurenOFC/pull/168), base A.
- [C #169 — evidências](https://github.com/Yamatosemj/aurenOFC/pull/169), base B.
- [D #170 — sequências](https://github.com/Yamatosemj/aurenOFC/pull/170), base C.
- E/contexto e validação final: criada sobre D; identificador na entrega.

As candidatas anteriores continuam dependências não integradas. Não reaplicar
commits nem mesclar a cadeia automaticamente. A instalação pessoal original
não foi substituída; nenhuma aprovação de deploy ou merge foi presumida.

Pendentes: latência/decisões com modelo real, geração de lotes pelo modelo,
YouTube público, navegação autenticada, fechamento contextual real e uso
prolongado. Outras ferramentas Windows legadas não foram migradas em massa.
Descoberta recursiva mantém limite de 20 s; atalhos/filesystem não têm deadline
absoluto. ShowWindow síncrono em aplicativo travado pode bloquear: os 300 ms
limitam a observação, não essa chamada nativa anterior. Fallbacks prévios por
processo/ASR foram preservados; não se promete resolver toda ambiguidade de
identidade no Windows. Nenhum desses limites foi ocultado com sucesso textual.
