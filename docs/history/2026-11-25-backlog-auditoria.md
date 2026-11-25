# Backlog técnico — auditorias de 25/11/2026

Base de leitura estática: [8158bf2](https://github.com/Yamatosemj/aurenOFC/commit/8158bf2c5add23508026ccb235d1854ace9c1e32). Transição documental integrada pela [PR #186](https://github.com/Yamatosemj/aurenOFC/pull/186). Este backlog não autoriza implementação ou merge em massa. Nenhum novo pytest, benchmark, teste físico ou Live foi executado durante as auditorias. O CI anterior não prova ausência dos defeitos aqui levantados. Os 45 itens originais incluem lacunas funcionais e de validação, não 45 bugs.

**Classificação:** D = comportamento demonstrável por leitura do código, ainda sem reprodução independente nesta auditoria; R = risco/hipótese a reproduzir; L = lacuna de funcionalidade ou validação; O = oportunidade de melhoria. Prioridade P0 = investigar segurança potencialmente bloqueante; P1 = relevante para primeira entrega cotidiana; P2 = polimento orientado por evidência; P3 = futuro. Prioridade não equivale a gravidade comprovada. Todos começam abertos, sujeitos a revisão contra main e testes existentes.

## Segurança e privacidade

| ID | Achado / fonte | Tipo / prioridade | Evidência de encerramento |
|---|---|---|---|
| S01 | Identidade do arquivo entre autorização e execução: tools/dispatcher.py, core/permission_manager.py, tools/file_intelligence.py | Confirmado por mocks (relato Codex) / P0 | Regressão deve negar mudança de destino em AUTO e CONFIRM, preservar bloqueios e caminho normal; avaliar separadamente corrida na abertura. |
| S02 | Marcação de fontes não confiáveis cobre conjunto específico de ferramentas: tools/dispatcher.py | R / P0 | Mapear todas as fontes e testar propagação, leitura e efeitos subsequentes; demonstrar proteção efetiva sem tornar conteúdo externo autorização. |
| S03 | Detecção de credenciais por termos: memory/store.py | D / P2 | Testes com dados sintéticos; política explícita para histórico, fatos e estratégias, sem prometer detectar todo segredo. |
| S04 | Confirmação falada pode consumir captura sem vínculo temporal explícito: voice/confirmation.py | R / P1, bloqueante para confirmação passiva | Testar áudio antigo, áudio durante TTS e solicitação nova; negar confirmação sem vínculo válido. |
| S05 | Redação heurística dos logs: core/harness_logging.py, core/harness_runtime.py | R / P2 | Exercitar valores sintéticos em logs e traces; minimizar dados e declarar limites. |
| S06 | Identidade UIA entre preflight e execução: tools/dispatcher.py, tools/windows_uia.py | R / P0 | Reproduzir troca de controle/alvo; negar mudança de identidade protegida ou exigir autorização adequada. |

### S01 — reprodução reportada em 25/11/2026

O proprietário trouxe o parecer do Codex sobre a main `2d1ac70`. Com arquivos sintéticos e resolução controlada por mocks, a leitura e a inspeção passaram de caminho permitido para externo sem confirmação; também foi possível ler destino externo B após confirmação de outro destino externo C. Destino sensível (.ssh) e confirmação negada continuaram bloqueados. O problema lógico de vinculação de autorização foi reproduzido; exploração por troca de link real não foi validada (Windows recusou criação do link). Não houve teste Live, mudança de runtime ou merge nessa investigação.

Testes offline relevantes reportados: 77 aprovados, 1 ignorado, após repetir fora de AppData; primeira execução teve 28 falhas por política de caminhos do diretório temporário. Limpeza de pasta sintética temporária foi bloqueada pela política local; não contornar essa proteção. Os resultados são relato do executor local, não uma execução independente desta auditoria.

Próxima tarefa: vincular autorização a destino canônico único, tanto AUTO quanto CONFIRM, incluindo destino apresentado na confirmação; rejeitar mudança de destino sem nova autorização, cobrir leitura e inspeção por regressão determinística e preservar bloqueios. A janela residual entre validação e abertura pelo SO deve ser explicitamente avaliada e não declarada resolvida por mera comparação textual.

### S01 — PAUSADO em 25/11/2026 (decisão do proprietário)

A correção inicial está na [PR #188](https://github.com/Yamatosemj/aurenOFC/pull/188), aberta em rascunho, HEAD `a9ab0f7`. Os três checks desse HEAD passaram, mas a revisão técnica permanece pendente. O proprietário reportou bloqueios recorrentes de respostas do Codex durante a revisão; a causa não foi confirmada. Há alterações locais de testes ainda não publicadas, que devem ser preservadas. O trabalho independente de métricas foi autorizado enquanto a questão é tratada.

**Retomada:** recuperar o estado local e a revisão pendente da PR #188, concluir a validação e obter CI no HEAD revisado e aprovação explícita antes de qualquer merge. Não considerar S01 encerrado nem reduzir sua prioridade P0; manter as restrições de segurança e de liberação registradas. Daybreak/suporte serão avaliados separadamente pelo proprietário. Retomar assim que possível, inicialmente previsto para 26/11/2026.

## Núcleo e execução

| ID | Achado / fonte | Tipo / prioridade | Evidência de encerramento |
|---|---|---|---|
| N01 | from_legacy e fast path inferem sucesso por texto; retorno vazio pode virar sucesso: core/tool_result.py, core/harness_fast_path.py | D / P1 | Reproduzir retorno vazio/erro não reconhecido; migrar caminho de mídia para contrato estruturado, preservando compatibilidade e distinguindo efeito incerto. |
| N02 | Cancelamento cooperativo de operações bloqueantes: core/task_manager.py, core/harness.py, providers/openai_provider.py | D / P1 | Testar cancelamento durante espera e impedir novas ações após cancelamento; documentar limites de operações já iniciadas. |
| N03 | Fallback experimental de áudio após erro de execução: core/capability_audio_runtime.py, auren.py | R / P1 | Testar falha anterior/posterior ao efeito e negação; impedir repetição de efeito incerto ou contorno de autorização. |
| N04 | WAITING não persiste após reinício | L / P3 | Se aprovado futuramente, recuperação segura sem renovar orçamento ou autorização. |
| N05 | Timeout/retries explícitos do provider só no modo de teste: providers/openai_provider.py | D / P2 | Medir falhas de rede e definir orçamento previsível de espera e tentativas sem repetir efeitos. |
| N06 | Heurísticas textuais de intenção: core/local_decision.py, core/intent_resolver.py | O / P2 | Corpus de frases inequívocas, negativas, compostas e ambíguas; abstenção correta. |
| N07 | Validação Live pós-#185 pendente | L / P2 (P0 se defeito no núcleo for reproduzido) | Cenários autorizados com SHA e logs; ver registro de transição. |

## Windows e mídia

| ID | Achado / fonte | Tipo / prioridade | Evidência de encerramento |
|---|---|---|---|
| W01 | Pausa/reprodução mapeadas para alternância: tools/windows_input.py, core/tools_registry.py | D / P1 | Pausar reproduzindo e já pausado sem retomar. |
| W02 | Envio de tecla não comprova playback: tools/windows_input.py | D / P1 | Consultar estado posterior da sessão; comunicar falha/incerteza honestamente. |
| W03 | Tecla de mídia global não seleciona sessão explicitamente | D / P1 | Testar zero, uma e múltiplas sessões, sem agir em alvo ambíguo. |
| W04 | Entrada global sem comprovação de recebimento pelo aplicativo | L / P2 | Quando observável, validar consequência; não equiparar evento enviado a ação realizada. |
| W05 | Exceção pode impedir soltura de tecla: tools/windows_input.py | R / P2 | Injetar exceção e comprovar tentativa de soltura das teclas pressionadas. |
| W06 | Volume/mudo sem leitura posterior: tools/windows_audio.py | D / P1 na expansão de áudio | Validar estado lido após mudança, inclusive falhas. |
| W07 | Correspondência aproximada de janela/controle: tools/windows_window.py, tools/windows_uia.py | R / P2 | Testar alvos duplicados e alteração de identidade; não agir em alvo ambíguo. |

## Voz e wake word

| ID | Achado / fonte | Tipo / prioridade | Evidência de encerramento |
|---|---|---|---|
| V01 | Wake word fora do runtime: experimental/wake_word.py | L / P1 | Integrar detecção local opt-in e demonstrar comando completo. |
| V02 | Distância de edição até dois para palavra de cinco letras: experimental/wake_word.py | D / P1 | Medir falsos acionamentos e rejeições em corpus PT-BR; avaliar alternativa antes de integrar. |
| V03 | Captura ativa pode incluir TTS, proteção é de pre-roll: voice/input.py | R / P1 | Testar reprodução simultânea e ausência de autoativação/confirmação. |
| V04 | Fila de áudio sem tamanho explícito: voice/main.py | D / P1 | Limitar fila e política de descarte sem descartar autorização válida. |
| V05 | Comandos podem envelhecer na fila sequencial: voice/main.py | R / P1 | Testar timestamps/gerações, atraso e descarte; não executar áudio obsoleto. |
| V06 | Reconhecimento com ruído/música não comprovado | L / P1 | Ensaios físicos autorizados com música, silêncio e ruído. |
| V07 | Consumo em escuta permanente desconhecido | L / P1 | Medir CPU/RAM em repouso e uso, comparar desligado/ligado. |
| V08 | Latência ponta a ponta insuficientemente medida | L / P1 | Medir captura, ASR, decisão, execução, verificação e início da resposta separadamente. |
| V09 | Recuperação de desconexão de microfone não validada | L / P2 | Testar desconectar/reconectar e informar indisponibilidade. |
| V10 | Atalho de desligamento/reativação e descarte passivo ainda não implementados | L / P1 | Testar alternância global, indicação, ausência de eventos tardios e PTT independente conforme #186. |

## Navegador

| ID | Achado / fonte | Tipo / prioridade | Evidência de encerramento |
|---|---|---|---|
| B01 | Seleção aproximada por papel/texto e índice: tools/browser_elements.py | R / P2 | Testar duplicatas, índice inválido e mudança de DOM; não selecionar alvo diferente. Conferir #176 antes de alterar. |
| B02 | Falha pontual pode reiniciar contexto inteiro: tools/browser.py | D / P2 | Testar timeout/erro pontual sem perda desnecessária de abas ou repetição indevida. |
| B03 | Espera fixa de 250 ms para novas abas: tools/browser_elements.py | D / P2 | Testar popup tardio e vínculo ao evento de abertura. |
| B04 | Estado global do navegador: tools/browser.py | O / P3 | Testar isolamento e ciclo de vida se houver concorrência; não refatorar sem necessidade. |
| B05 | Validação Live pós-#185 pendente | L / P2 | Mesmo escopo de N07; não duplicar trabalho. |
| B06 | Destino técnico não comprova relevância semântica | L / P3 | Avaliar qualidade de seleção em corpus quando necessário. |
| B07 | Cobertura limitada de desafios antibot | L / P2 | Reproduzir padrões observados, preservar intervenção humana; não contornar CAPTCHA. |

## Memória, desempenho e manutenção

| ID | Achado / fonte | Tipo / prioridade | Evidência de encerramento |
|---|---|---|---|
| M01 | Consulta carrega todos os fatos antes de classificar: memory/store.py | D / P2 | Benchmark com bancos sintéticos crescentes antes de indexar. |
| M02 | SQLite sem criptografia própria da aplicação identificada | L / P2 | Definir ameaça, retenção e proteção local; não inferir que disco pessoal esteja desprotegido. |
| M03 | Política de retenção de logs não identificada no escopo revisado | R / P2 | Mapear retenção/rotação, limites e privacidade. |
| M04 | Logs truncados dificultam diagnóstico (evidência #185) | D / P2 | Registrar metadados estruturados suficientes sem despejar segredos. |
| M05 | Mídia simples depende do modelo no caminho padrão: core/local_decision.py | D / P1 | Comando inequívoco por executor compartilhado, sem API; ambíguo deve abster/esclarecer. |
| M06 | Estado operacional desatualizado | D / P2 | #186 atualizou a prioridade, mas mantém contexto antigo marcado como histórico; reconciliar fatos vigentes quando necessário. |
| M07 | PRs antigas abertas/escopos sobrepostos | D / P2 | Triar contra main; não mesclar ou fechar em massa. |
| M08 | Consumo prolongado desconhecido | L / P2 | Ensaios de duração, crescimento de RAM/logs, recuperação e encerramento. |

## Polimento adicional identificado na segunda auditoria

| ID | Achado / fonte | Tipo / prioridade | Critério |
|---|---|---|---|
| P01 | Contexto completo antes de tentar fast path: core/harness.py, core/session.py | D / P2 | Medir custo atual e preparar contexto seletivo sem quebrar esclarecimento, autorização ou trace. |
| P02 | Voz processada em sequência, pesquisa pode atrasar pausa: voice/main.py | D / P2 | Medir espera; depois, prioridades e exclusão por recurso, sem segundo executor nem paralelismo irrestrito. |
| P03 | Regras de intenção/capacidades em múltiplos componentes | O / P2 | Mapear responsabilidades; consolidar somente duplicações comprovadas, progressivamente. |
| P04 | Verificação heterogênea de consequências | O / P1 | Aplicar primeiro à mídia; observar alvo/estado, executar se necessário, reobservar e distinguir resultado incerto. Relacionado a N01/W01-W03. |
| P05 | Busca de histórico por janela recente e relevância textual | D / P3 | Medir recuperação em corpus sintético; manter SQLite, avaliar índice e atualidade antes de banco vetorial. |
| P06 | Custo de tokens calculado com preços fixos: core/usage.py | D / P2 | Configuração de preço por modelo, declarar estimativa e testar troca de modelo. |
| P07 | Trace grava spans de forma síncrona: core/task_trace.py | D / P2 | Quantificar sobrecarga antes de otimizar escrita; preservar durabilidade necessária. |
| P08 | Relatório converte total_ms ausente para zero: core/task_trace.py | D / P1 para baseline | Reproduzir tarefa incompleta; excluir/relatar separadamente e testar percentis. |
| P09 | Métricas de voz parcialmente separadas do trace | L / P1 para baseline | Vincular captura/ASR/execução/TTS a uma tarefa e distinguir sucesso e falha. |
| P10 | Ciclo de vida de processo permanente | L / P2 | Testar suspensão, rede, dispositivos, ociosidade e desligamento; relacionado a M08/V07/V09. |

## Plano de entrega — 25/11/2026

Priorizar experiências utilizáveis, em vez de encerrar todos os 55 achados antes do uso. As pendências abaixo não autorizam implementação simultânea nem alteram os critérios de segurança.

- [x] P08 — corrigir população das estatísticas. [PR #189](https://github.com/Yamatosemj/aurenOFC/pull/189) integrada na main em `03d1c8e`; três checks do HEAD revisado aprovados. Validação Live fora do escopo.
- [x] Contabilização de chamadas ao modelo — distinguir rodadas, chamadas ao provider, verificação de intenção, cache local, falhas e uso desconhecido. [PR #190](https://github.com/Yamatosemj/aurenOFC/pull/190) integrada em `661f9b1`; três checks do HEAD revisado aprovados. Sem Live; retries internos e custos desconhecidos permanecem limites.
- [ ] P06 — estimativas de custo por modelo, sem tratar preço desconhecido como custo zero.
- [ ] P09/V08 — métricas mínimas de voz e latência ponta a ponta; detalhar estágios apenas quando necessários.
- [ ] P07 — medir sobrecarga no ambiente alvo quando autorizado; adiar alteração de arquitetura sem evidência de impacto.
- [ ] S01 (pausado, P0), S02/S06 e demais bloqueios de segurança relevantes — retomar prioritariamente assim que possível; não liberar uso cotidiano com bloqueios efetivos pendentes.
- [ ] Estudar soluções de voz atuais do Ari e de projetos comparáveis, incluindo licença e adequação ao ambiente alvo.
- [ ] Entregar primeiro comando local de mídia, com confirmação do estado real, sem chamada paga para comando inequívoco (N01/N03, W01–W03, M05/P04 conforme aplicável).
- [ ] Integrar ativação por nome opt-in e atalho global, preservar PTT, validar escuta e segurança (V01–V06/V10, S04; V07/V08).
- [ ] Iniciar uso cotidiano após validação autorizada; priorizar problemas observados. Restante do backlog permanece aberto e não é condição geral para a primeira entrega.

S01 não perde prioridade por estar abaixo das métricas nesta lista: a pausa é temporária, e a retomada de segurança precede a liberação. Cada tarefa em PR própria, revisão e aprovação explícita antes de merge. A ordem antiga abaixo permanece como referência técnica, subordinada a este plano de entrega.

## Ordem de trabalho proposta

1. S01 reproduzido por mocks conforme parecer local acima; correção inicial em revisão, temporariamente pausada conforme registro de 25/11. Retomar antes de liberar o uso cotidiano com segurança pendente. Depois investigar S02 e S06 conforme reprodução; reclassificar se não houver bloqueio efetivo. Segurança compartilhada comprovadamente comprometida bloqueia avanço. Não presumir outros bypasses.
2. N01/N03 e métricas mínimas de referência para a mídia, com mudanças pequenas e focadas.
3. W01-W03 + M05/P04: uma pausa real e local; reaproveitar Dispatcher, contratos, PermissionManager e ToolResult.
4. V01-V06/V10, incluindo S04 e medição V07/V08: wake word local, atalho e validação física autorizada; expansão só após a primeira experiência.
5. Polimento restante por impacto medido e uso real, sem reescrita do núcleo nem correção em massa. Manter PRs e pendências de navegação anteriores abertas até evidência suficiente.

Para cada item: conferir main e PRs existentes, formular hipótese, reproduzir antes de corrigir, registrar teste falhando (ou resultado negativo), correção focalizada em PR própria, teste de regressão, CI no HEAD e validação Live somente quando expressamente autorizada. Itens podem ser relacionados sem duplicar trabalho. Não marcar resolvido por inspeção ou promessa.
