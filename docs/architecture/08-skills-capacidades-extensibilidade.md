# Arquitetura 08 — Skills, catálogo de capacidades e extensibilidade

> **Etapa 8 — auditoria estática** da `main` no commit `186b783965229a2578191a7337d4ed82228e0923` (2026-10-10). **Código existente ≠ habilitado ≠ testado em CI ≠ validado no computador real.** Esta PR documenta o estado atual; não instala skills, ativa flags, conecta plugins, executa ferramentas locais, altera permissões ou adiciona capacidades.
>
> Leia também [01 — Harness](01-nucleo.md), [02 — Dispatcher e política](02-roteamento-seguranca.md), [03 — sessão e contexto](03-modelo-sessao-memoria.md), [06 — voz](06-voz-stt-tts.md) e [07 — GUI](07-interface-desktop-gui.md). Aqui, **skill textual**, **Capability declarada**, **Tool registrada**, **Fast Path** e **experimento** são coisas distintas.

## 1. Mapa de responsabilidades

| Fonte | Responsabilidade verificada | Estado |
| --- | --- | --- |
| [`skills/loader.py`](../../skills/loader.py) | Instala localmente, descobre, seleciona e resume documentos `SKILL.md` para contexto do modelo | **Carregador integrado** ao contexto; não há `skills/**/SKILL.md` versionado nesta revisão |
| [`skills/__init__.py`](../../skills/__init__.py) | Reexporta `Skill` e `SkillLibrary` | Presente |
| [`core/session.py`](../../core/session.py) | Inclui seção `skills` no contexto da tarefa via `prompt_context(objetivo)` | Integrado; depende de haver conteúdo local correspondente |
| [`core/capabilities.py`](../../core/capabilities.py) | Define 14 `Capability`s, metadados, padrões de intenção e tools correspondentes | **Catálogo declarativo**, não registro de funções executáveis |
| [`core/task_spec.py`](../../core/task_spec.py) | Esquema JSON e validação de `TaskSpec` v1; limites de tentativa e esclarecimento | Utilizado pelo caminho do resolver/experimento |
| [`core/intent_resolver.py`](../../core/intent_resolver.py) | Converte `TaskSpec` válido em intenção e argumentos por regras lexicais/estruturadas | Utilizado pelo resolver |
| [`core/capability_resolver.py`](../../core/capability_resolver.py) | Confere Capability, parâmetros, rota `local` ou `luna` e sinal de confirmação efetiva | Disponível por `Router.route_task_spec` |
| [`core/router.py`](../../core/router.py) | Seleção normal de ferramentas/decisão local; expõe `route_task_spec` sem substituir roteamento atual | Rota normal permanece separada do experimento |
| [`core/local_decision.py`](../../core/local_decision.py) e [`tools/fast_paths.py`](../../tools/fast_paths.py) | Decisão de atalhos e execução **via Dispatcher** quando reconhecidos | Ativo no Harness |
| [`core/capability_audio_runtime.py`](../../core/capability_audio_runtime.py) | Flag opt-in para resolver apenas `controlar_audio` e montar tool calls pelo executor já injetado | **Experimento desativado por padrão** |
| [`core/capability_audio_experiment.py`](../../core/capability_audio_experiment.py) | Compara casos de resolução com baseline, sem executar tool ou modelo | Diagnóstico offline |
| [`experimental/wake_word.py`](../../experimental/wake_word.py) | Normalização, similaridade de termos e filtro energético de áudio | **Fora** do PTT ativo; não é hotword contínua |
| [`scripts/experimentos/`](../../scripts/experimentos/ATIVAR_EXPERIMENTO_AUDIO.bat) | Lançadores para ativar/desativar a flag só no processo iniciado | Scripts opt-in, não alteração permanente do Auren |

**Constatação na árvore:** esta `main` possui `skills/loader.py` e `skills/__init__.py`, mas **não** contém arquivos `SKILL.md` versionados em `skills/`. É possível haver skills locais não commitadas no computador de outra pessoa; essa possibilidade **não foi inspecionada**. Não inferir skills ativas com base apenas na presença do carregador.

## 2. Skills: instruções de contexto, não ferramentas

[`SkillLibrary`](../../skills/loader.py) usa `skills/` como raiz por padrão. O contrato de arquivo é simples: um `SKILL.md` pode conter front matter delimitado por `---` com linhas `name:` e `description:`; sem esses campos, nome cai para o nome da pasta e descrição para o primeiro texto não vazio do corpo (até **240 caracteres**).

- `discover()` procura recursivamente `SKILL.md` e ignora arquivos ilegíveis, links simbólicos/junctions e nomes inválidos; verifica que o documento resolvido permanece dentro da raiz. **Não** consulta catálogo remoto, não instala dependências e não executa código da skill.
- `match(objective, limit=3)` tokeniza a solicitação e classifica pelo **número de termos com ocorrência como substring** em nome, descrição ou corpo. Empate é por nome; isso **não** é ranking semântico nem comprovação de capacidade.
- `prompt_context(objective, limit=3, max_chars=2200)` concatena até **700 caracteres de instruções por skill**, com limite total de **2.200** e uma identificação explícita de conteúdo não confiável. `compact_descriptions(limit=8)` lista resumos, mas não executa ação.
- `install(source, name=...)` copia **somente** `SKILL.md` para a raiz escolhida. **Correção candidata do achado 6:** valida o nome do front matter e qualquer override de diretório como um único componente portátil, recusa nomes reservados no Windows, caminhos absolutos, separadores e travessia `..`; recusa fontes/destinos em links simbólicos e junctions, confere contenção após resolver caminhos e substitui `SKILL.md` via arquivo temporário e `os.replace` para não seguir um link no arquivo final. Não instala scripts ou contratos automaticamente.

### Onde o conteúdo entra

[`auren.py`](../../auren.py) monta um `SessionContextManager(memory_store, SkillLibrary())`; [`core/session.py`](../../core/session.py) compõe as seções `turnos, tarefa, fatos, memoria, estrategias, skills` nessa ordem, conforme orçamento. O [Harness](../../core/harness.py) consome o contexto; a seção de skills chega ao modelo **como texto**, não como ferramenta do registry nem como permissão elevada.

**Limites de confiança:** `prompt_context` rotula skills como dados não confiáveis, mas esse prefixo textual **não constitui isolamento forte** de prompt injection. Uma skill local com instruções perigosas não deve ganhar prioridade sobre políticas de sistema, usuário ou autorização por ser recuperada. Não existe validação de assinatura, sandbox de execução ou política de fontes explicitamente implementada por este carregador.

**Achado 6 — correção candidata:** a versão anterior aceitava `name`/front matter diretamente como caminho de destino, criando risco de travessia e redirecionamento por symlink. Agora há validação portátil de nome, contenção por `resolve` e rejeição de symlinks/junctions no destino e em `discover`. [Testes dedicados](../../tests/test_skills_path_safety.py) cobrem nomes hostis, front matter, reinstalação comum, links para fora, links internos e fonte redirecionada em `tmp_path`. **Limitação:** o diretório de skills deve pertencer ao usuário confiável; checagens de caminho e `os.replace` não tornam a operação race-proof diante de outro processo que consiga substituir diretórios simultaneamente, nem autenticam o conteúdo da skill.

## 3. Catálogo de capacidades e resolver — 14 definições ≠ 49 tools

[`CAPABILITY_REGISTRY`](../../core/capabilities.py) registra 14 capacidades com `id`, descrição, metadados de local/determinística/múltiplas etapas/raciocínio, parâmetros obrigatórios/opcionais, sinal de confirmação, resolver, lista de tools, prioridade e padrões regex de objetivo:

`abrir_programa`, `abrir_url`, `pesquisar_web`, `interagir_com_browser`, `tocar_musica_spotify`, `gerenciar_abas`, `controlar_janela`, `controlar_audio`, `consultar_status_windows`, `analisar_tela`, `localizar_arquivo`, `inspecionar_arquivo`, `ler_arquivo` e `memoria_persistente`.

Esses registros **agrupam tools reais**. As **49 ferramentas** utilizáveis são definidas em [`core/tools_registry.py`](../../core/tools_registry.py), validadas por [`core/tool_contracts.py`](../../core/tool_contracts.py), autorizadas por [`core/permission_manager.py`](../../core/permission_manager.py) e chamadas pelo [`tools/dispatcher.py`](../../tools/dispatcher.py). Uma Capability nova no catálogo **não** implementa uma tool nova nem a insere automaticamente no ciclo normal.

Fluxo declarativo:

```text
TaskSpec v1 (core/task_spec.py)
  → validate_task_spec()
  → IntentResolver: padrões + dados exatos
  → CapabilityResolver: id, campos obrigatórios e rota
       ├─ local: capacidade declarada local/determinística/etapa simples
       └─ luna: depende de raciocínio, várias etapas ou regra não local
  → resultado descritivo da resolução (não executa tool por si)
```

`MAX_TASKSPEC_VALIDATION_ATTEMPTS=2` e `MAX_CAPABILITY_CLARIFICATION_ROUNDS=2`; `CapabilityResolver` retorna status `invalid`, `clarification`, `unresolved` ou `resolved`. `IntentResolver` dá preferência a `dados_exatos` quando há colisão com `parametros` e faz extração por padrões, não por uma chamada à API. Para um pedido desconhecido, pode permanecer não resolvido; uma classificação `local` **não garante** ação realizada.

**Importante sobre autorização:** `effective_confirmation()` calcula um **sinal de rota** conforme `always`, `never` ou `core_policy`. Isso **não revoga** a política real por ferramenta/argumentos do PermissionManager. O modelo ou uma Capability marcada `never` não podem autorizar uma ferramenta bloqueada.

## 4. Caminho ativo versus caminho experimental

O fluxo normal do Auren usa a fábrica [`auren.criar_harness`](../../auren.py), Router, heurísticas de [`LocalDecisionEngine`](../../core/local_decision.py), atalhos em [`tools/fast_paths.py`](../../tools/fast_paths.py) e, quando aplicável, o modelo; ações seguem **sempre** pelo Dispatcher.

`Router.route_task_spec` existe, mas o código o descreve como **não substituto do roteamento normal**. As escolhas de áudio (`set_volume`, `set_mute`, `control_media`) reconhecidas por `LocalDecisionEngine` não são promovidas automaticamente ao conjunto de atalhos executados pelo `tools/fast_paths.py` na configuração normal; esse conjunto contém status do sistema, abertura de abas, URLs e sites conhecidos.

Quando `AUREN_EXPERIMENT_CAPABILITY_AUDIO` assume um valor verdadeiro (`1`, `true`, `sim`, `yes`, `on`), [`try_execute`](../../core/capability_audio_runtime.py) é chamado pelo caminho de `comando_rapido` em `auren.py`:

1. Monta e valida TaskSpec com frase da solicitação.
2. Resolve intenção e exige `status=resolved`, `route=local` e `capability_id=controlar_audio`.
3. Converte `consultar`, `volume`, `mudo`, `mudo_off`, `play_pause`, `proxima` e `anterior` em **tool calls** já registradas.
4. Encaminha ao **`executar_ferramenta` injetado**, que leva ao Dispatcher → contrato → PermissionManager → ToolResult; valida tipo e `ok`.
5. Se não casar intenção ou a execução falhar, retorna `False` e permite que o caminho normal tente resolver a mensagem.

Portanto, **flag ativa não é autorização**, e o experimento **não** altera o pipeline PTT/STT/TTS. Ele é sobre volume/mudo/mídia do **Windows**, não sobre escuta contínua ou síntese de voz. O [`core/capability_audio_experiment.py`](../../core/capability_audio_experiment.py) executa apenas uma **matriz sintética de 12 frases**, comparando contagem/resolução com Router, sem ferramenta real, sem modelo e sem cobrança de tokens. Os scripts [ativar](../../scripts/experimentos/ATIVAR_EXPERIMENTO_AUDIO.bat) e [desativar](../../scripts/experimentos/DESATIVAR_EXPERIMENTO_AUDIO.bat) só preparam flag ambiental e chamam `py main.py` no processo lançado.

**Limite a validar em tarefa própria:** caso uma tool retorne erro após efeito físico parcial, o fallback para o caminho normal poderia tentar ação semelhante novamente. Isso é uma possibilidade de fluxo, **não** reprodução de dupla execução. Guardas, confirmação e proteção contra repetição precisam ser testados em cenários controlados antes de alterar fallback.

## 5. Wake word: experimento isolado

[`experimental/wake_word.py`](../../experimental/wake_word.py) implementa distância de edição, normalização de texto e extração de comando após uma possível palavra de ativação. O filtro de energia avalia áudio de 16 bits em janelas de 20 ms, duração aproximada entre **0,3 e 4,0 s** e propriedades de variação/atividade.

A árvore do projeto **não contém integração desse módulo no loop `voice/main.py`**; o modo de voz ativo usa push-to-talk, conforme [Etapa 6](06-voz-stt-tts.md). Não há serviço residente de hotword, captação contínua de comando, segurança contra voz sintética ou avaliação física de falso positivo comprovada por este arquivo. Não anunciar wake word como recurso existente do Auren.

## 6. Testes e grau de evidência

| Fonte | Escopo que o código de teste comprova quando passa |
| --- | --- |
| [`tests/test_capability_registry.py`](../../tests/test_capability_registry.py) | Conjunto esperado de 14 ids, tools referenciadas presentes no registry, resolução de TaskSpec e rotas, limites de esclarecimento/sinal de confirmação |
| [`tests/test_capability_audio_experiment.py`](../../tests/test_capability_audio_experiment.py) | 12 casos estáticos resolvidos localmente e comparação com Router existente, sem modelo |
| [`tests/test_capability_audio_runtime.py`](../../tests/test_capability_audio_runtime.py) | Flag desligada, conversão de argumentos, simulação de sucesso da ferramenta, fallback para pedidos não áudio |
| [`tests/test_task_spec.py`](../../tests/test_task_spec.py) | Esquema e falhas de TaskSpec v1 |
| [`tests/test_router_tool_selection.py`](../../tests/test_router_tool_selection.py), [`tests/test_routing_single_owner.py`](../../tests/test_routing_single_owner.py) | Seleção de tools e caminho único de execução em ambiente controlado |
| [`tests/test_prompt_injection.py`](../../tests/test_prompt_injection.py) | Guardas de conteúdo não confiável nos fluxos simulados; não equivale a isolamento das instruções recebidas em SKILL.md |
| [`tests/test_skills_path_safety.py`](../../tests/test_skills_path_safety.py) | Instalação/descoberta em `tmp_path`: nomes válidos e hostis, travessia de caminho, symlink/junction, conteúdo dentro/fora da raiz e ausência de escrita externa; não testa corrida hostil nem valida o conteúdo semântico |

Não existe arquivo `tests/test_skills.py` nem `SKILL.md` versionado nesta árvore; isso **não significa** que o carregador é seguro ou inseguro sem teste adicional. A auditoria consistiu em leitura dos códigos e testes citados. O primeiro HEAD revisado da PR #128 (`d56255cdd28d0517b2027ca898180f5a9a04a645`) passou no CI hospedado: [suíte Linux completa](https://github.com/Yamatosemj/aurenOFC/actions/runs/38097910114) (**556 passed, 24 skipped**) e [focados Linux/Windows](https://github.com/Yamatosemj/aurenOFC/actions/runs/38097910125) (Linux **166 passed/15 skipped**, Windows **181 passed**, modo seguro **110 passed** por sistema). **Reverificar CI do SHA final antes de integrar.** Aprovação com mocks não demonstra execução do experimento no Windows pessoal, autenticação de fonte da skill, instalação segura com nomes maliciosos ou comportamento real do wake word.

## 7. Guia de extensão sem romper o núcleo

### Adicionar uma skill textual

- Criar `skills/<nome>/SKILL.md` apenas a partir de fonte confiável/revisada, com nome, descrição e instruções delimitadas; lembrar que esse texto será incluído no contexto **como dado**, não como comando autorizado.
- Testar `discover`, `match`, limites de contexto, concorrência lexical, codificação e tentativa de instrução adversarial. Não instalar anexos ou executar scripts só porque a skill os mencionou.
- Se `install` for usado para fontes externas, **validar fronteira do diretório, origem e symlinks** antes de habilitar fluxo de instalação de terceiros.

### Adicionar uma capacidade executável

- Definir se basta uma *intenção* que use ferramentas existentes ou se realmente é necessária uma **tool nova**. Se houver tool nova, alinhar [registry](../../core/tools_registry.py), [contratos](../../core/tool_contracts.py), [Dispatcher](../../tools/dispatcher.py), [PermissionManager](../../core/permission_manager.py), Router, ToolResult, guardas e testes.
- Preservar `Harness → Router → Dispatcher → contrato → permissão → handler → ToolResult`. Nem Capability, skill ou fast path executam direto fora desse fluxo.
- Manter funcionalidades sensíveis e experimentos atrás de política/flag e registrar riscos, testes de falha, regressão, custo e rollback em PR própria.

### Promover um experimento

- Distinguir **experimento offline**, **flag opt-in**, **padrão de produção**, **CI simulado** e **Live/hardware autorizado**.
- Registrar resultados em SHA, escopo e ambiente específicos; não converter estatísticas de 12 frases em promessa de acerto universal.
- Desenhar teste de efeitos parciais/fallback e confirmar que políticas não foram afrouxadas; só depois decidir se uma função merece ativação por padrão.

## 8. Pendências delimitadas (não corrigir nesta PR)

1. **Skills sem bateria dedicada:** seleção lexical, front matter, tamanho, nome de pasta e fronteiras de caminho/symlink merecem testes independentes.
2. **Instruções locais como texto não confiável:** guarda contra prompt injection precisa de cenários adversariais de skill reais; prefixo no prompt não substitui isolamento/política.
3. **Catálogos diferentes:** `KNOWN_SERVICES` do catálogo de capacidades e `SITES_CONHECIDOS` dos fast paths não são a mesma lista; alterações futuras podem criar comportamento inconsistente.
4. **Limite do experimento áudio:** fallback após erro, idempotência e custo de repetição de comando devem ser avaliados antes de expandir uso.
5. **Wake word:** permanece fora do runtime; falta validação de microfone real, falsos positivos, consumo e privacidade antes de considerar habilitação.
6. **Runtime:** não existe sistema genérico de plugins com execução arbitrária criado automaticamente pelo carregador de SKILL.md; novas integrações exigem arquitetura e política explícitas.

**Próxima etapa documental após esta:** **Etapa 9 — testes, CI e controle remoto**, em PR separada.
