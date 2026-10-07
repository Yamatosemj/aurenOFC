# Referência Mark-LV → Auren

> Mark-LV é usado somente como referência de problema, comportamento desejado e casos-limite. O projeto Mark-LV está licenciado sob **CC BY-NC 4.0**. O Auren não deve copiar código ou comentários do Mark; cada solução deve ser reescrita com a arquitetura do Auren, nomes em português e `ToolResult`.

## Mapa de trabalho

| Tarefa | Ideia do Mark-LV | Arquivo(s) do Mark | Arquivo-alvo no Auren | Status |
|---|---|---|---|---|
| **1** | Timeout, retry, escada de modelos e cooldown por classe de falha | `core/gemini.py` | `providers/model_ladder.py`, `providers/openai_provider.py`, `config.py`, `core/usage.py`, testes de provider/modelo | **PRÓXIMA — especificada neste guia** |
| **2** | Memória recuperável sob demanda, com índice pequeno no prompt e busca local | `main.py`, `memory/memory_manager.py` | `memory/store.py`, `tools/memory.py`, integração existente de memória | **PARCIAL — Auren já possui memória persistente; falta auditar/implementar a ideia de recuperação sob demanda** |
| **3** | Undo único e reversível, sem guardar dados gigantes | `core/undo.py` | `core/` + ferramentas reversíveis que já passam pelo Dispatcher | **BACKLOG — não implementar nesta etapa** |
| **4** | Confirmação humana que o modelo não consegue forjar | `core/confirm.py`, `ui.py` | `core/permission_manager.py`, `voice/confirmation.py`, fluxo de confirmação existente | **PARCIAL — Auren já tem infraestrutura de permissão/confirmação; desenho não-forjável ainda precisa de tarefa própria** |
| **5** | Seleção e medição de microfone/alto-falante, com fallback determinístico | `core/audio_devices.py` | `voice/input.py`, `voice/tts.py`, novo módulo de seleção de dispositivos se necessário | **BACKLOG — não existe especificação de implementação ainda** |
| **6** | Continuidade de sessão/resumption em reconexão, sem ressuscitar conversa antiga indevidamente | `main.py` | `providers/openai_provider.py`, `core/harness.py`, `memory/store.py` | **BACKLOG — requer verificação da semântica da API antes de codificar** |
| **7** | Wake word local + push-to-talk/acknowledgment com concorrência controlada | `core/wake_word.py`, `core/hotkey.py`, `main.py` | `voice/input.py`, `voice/`, `experimental/wake_word.py` apenas como referência do que já existe | **PARCIAL — wake word experimental existe, mas não faz parte do caminho normal** |
| **8** | Avatar, acting facial, visemes/lip-sync | `core/avatar.py`, `core/viseme.py`, `ui.py` | Nova camada visual do Auren (alvo ainda a definir), integrada ao fluxo normal | **BACKLOG — não há tarefa de UI/runtime definida** |
| **9** | Vídeo no HUD + theming/configuração visual | `ui.py` | Nova camada visual/configuração do Auren (alvo ainda a definir) | **BACKLOG — escopo visual separado do runtime atual** |
| **10** | Continuidade/uso remoto e extensões de longo prazo (histórico, remoto, integrações) | `readme.md` — roadmap LVI+ | Futuro módulo de transporte/remoto + `core/harness.py` conforme escopo de cada integração | **BACKLOG — ideias de longo prazo, sem implementação silenciosa** |

## Notas de interpretação

**Tarefa 1** é a única tarefa técnica detalhada no guia atual e, portanto, é a única pronta para execução depois do kit de continuidade.

**Tarefas 2–10** são uma decomposição de planejamento baseada no roadmap público do Mark-LV, não uma autorização automática de implementação. Quando uma delas virar tarefa ativa, ela deve ganhar especificação própria, arquivos concretos após inspeção e testes de regressão.

O princípio arquitetural do Auren permanece soberano: **Router → Dispatcher → Contrato → Permissão → Ferramenta → ToolResult**.
