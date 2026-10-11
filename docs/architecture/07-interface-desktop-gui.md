# Arquitetura 07 — Interface desktop (Tkinter) e backend GUI

> **Etapa 7 — auditoria estática** da `main` no commit `89755a2705b08b241e9f5e019b62f41ccda3d30d`. A presença de uma GUI, de seus estados e de testes com doubles **não comprova funcionamento visual no Windows real**. Esta revisão não executou janela física, API paga, automação desktop nem o notebook pessoal do proprietário. Só documenta contratos existentes.
>
> Documentos anteriores: [núcleo/Harness](01-nucleo.md), [Dispatcher e autorização](02-roteamento-seguranca.md), [sessão e memória](03-modelo-sessao-memoria.md) e [Windows/UIA](04-windows-arquivos-visao.md). A GUI é um **canal de entrada de texto** do mesmo Auren; não é um segundo agente nem inclui PTT. Para voz, consulte [Etapa 6](06-voz-stt-tts.md).

## 1. Mapa de ownership

| Código | Responsabilidade observada |
| --- | --- |
| [`interface_auren.py`](../../interface_auren.py) | Criação da janela Tkinter, conversa visível, botões de modo, envio, exibição de eventos e diálogo de confirmação; só manipula widgets no thread de UI |
| [`ui/backend.py`](../../ui/backend.py) | Worker daemon serializado, filas `Queue` de comandos/eventos, geração de sessão, confirmação como canal injetado, encaminhamento ao Harness e descarte da sessão |
| [`ui/__init__.py`](../../ui/__init__.py) | Marca pacote; nenhuma rota alternativa |
| [`scripts/iniciar/ABRIR_AUREN_GUI.bat`](../../scripts/iniciar/ABRIR_AUREN_GUI.bat) | Entra na raiz do projeto e chama `py -3 interface_auren.py`, com fallback `python` se o lançador `py` não existir |
| [`auren.py`](../../auren.py) | `criar_harness(confirmation_channel=...)`, fábrica compartilhada com CLI/voz, preservando Router → Dispatcher → contrato → PermissionManager → executor → ToolResult |
| [`core/confirmation.py`](../../core/confirmation.py) | `ConfirmationRequest` e `ConfirmationChannel`; o backend GUI implementa apenas esse canal |
| [`core/harness.py`](../../core/harness.py), [`core/task_manager.py`](../../core/task_manager.py) | Tarefa, snapshot, cancelamento **cooperativo** e encerramento da sessão do Harness |
| [`tests/test_desktop_ui_backend.py`](../../tests/test_desktop_ui_backend.py) | Contratos sintéticos de worker, confirmação e sintaxe do frontend |

A interface é Tkinter padrão, inicializada por `main()` em `interface_auren.py`. A janela abre em `off` (Desligado) com título `Auren · Desktop`, tamanho inicial **870 × 620** e mínimo **610 × 430**. Exibe cabeçalho/versão V47, estados, conversa e caixa de entrada. A interface não inicia automaticamente o modo voz; não fornece captura de microfone, hotword nem áudio em tempo real.

## 2. Fronteira entre UI, thread worker e Harness

```text
Tkinter (thread principal)
   ├─ usuário: selecionar modo, digitar e clicar Enviar
   ├─ enviar texto → AurenUiWorker.submit() → Queue de pedidos
   ├─ _poll() a cada 80 ms ← Queue de UiEvent
   └─ diálogo de autorização → ConfirmationChoice.answer(True / False)

AurenUiWorker (uma thread daemon)
   ├─ _run() retira um pedido por vez
   ├─ cria Harness tardiamente via auren.criar_harness(
   │      confirmation_channel=GuiConfirmationChannel(...)
   │   )
   ├─ harness.processar_mensagem(texto)
   ├─ harness.current_task() → estado para erro/resposta
   ├─ UiEvent("busy" / "reply" / "error" / "idle")
   └─ "off"/"quit" → _dispose_harness()

Execução de ação pelo Harness
   → Router → Dispatcher → ToolContract → PermissionManager
   → [GuiConfirmationChannel.confirmar() em ações CONFIRM]
   → executor da tool → ToolResult → Harness
```

`AurenDesktop.__init__` inicia `worker.start()` ao montar a janela. **Isso não cria o Harness nem conecta imediatamente à API**: em `AurenUiWorker._run`, `_make_harness` só é chamado quando chega uma mensagem válida. O worker pode receber uma factory falsa para testar, e o canal é injetado na factory via parâmetro `confirmation_channel`.

Há **duas filas** distintas:
- `_requests` recebe tuplas `("message", texto, geracao)`, `("off", "", geracao)` e `("quit", "", geracao)`;
- `events` devolve objetos `UiEvent(kind, text, payload)`. Tipos produzidos/consumidos: `busy`, `idle`, `reply`, `error`, `notice`, `confirm`, `confirm_done`, `off` e `closed`.

O thread do worker **não chama widgets Tk**. O frontend faz `_poll()` via `root.after(80, ...)`, esvaziando até **80 eventos** por rodada e marcando próximo polling. Isso reduz chamadas Tk fora do thread principal, mas não garante entrega instantânea ou ausência de fila sob carga.

## 3. Três modos visíveis — sem confundir com TaskState

| Modo GUI | Ação observada | Implicações e limites |
| --- | --- | --- |
| **Desligado** (`off`) | Estado inicial. Campo e botão Enviar desabilitados. Ao transicionar de outro modo, chama `worker.go_off()`, nega confirmação pendente e descarta modal | `go_off` desabilita worker, aumenta `_generation`, pede cancelamento e enfileira `off` para liberar o Harness **quando o worker chegar ao comando** |
| **Ativo** (`active`) | Chama `worker.activate()`, habilita envio quando não estiver `busy` ou `closing` | O Harness continua a ser criado no primeiro pedido, não no clique do botão Ativo |
| **Standby** (`standby`) | Desabilita campo/botão Enviar no frontend e atualiza rótulo | **Não** chama `worker.go_off()` nem `worker.cancel_current()`; worker continua `_enabled=True` se veio de Ativo, preserva Harness e pode concluir tarefa já em execução |

A variável `mode` descreve **o estado de interface**, não o `TaskState` do Harness (CREATED/RUNNING/WAITING/COMPLETED/FAILED/CANCELLED). `busy` e `closing` são flags de apresentação adicionais; a etiqueta exibida passa a PROCESSANDO durante tarefa e ENCERRANDO ao fechar.

**Lacuna de contrato a considerar antes de alterar código:** em `set_mode("standby")` o backend não recebe mudança equivalente. `submit()` no worker aceitaria novos pedidos por chamada direta após sair de Ativo para Standby, pois `_enabled` permanece verdadeiro; a GUI bloqueia seu próprio botão/Enter. Isso **não é pausa do processamento nem isolamento do backend**. A verificação desta lacuna é estática, sem teste visual real.

## 4. Envio, serialização e identificação de respostas

`send()` só chama `worker.submit(message)` quando `mode=="active"`, `busy==False` e `closing==False`. Texto vazio é ignorado. Pedido aceito limpa o campo, mostra a mensagem imediatamente, marca `busy` e desabilita novos envios visíveis.

O worker verifica `_enabled`, `_closing` e `_generation` antes de executar; um pedido antigo de outra geração é **descartado**. Após obter o Harness, confere novamente a geração antes de executar a mensagem. Isso evita iniciar várias operações obsoletas já enfileiradas, mas **não é uma fila de tarefas paralelas** nem prova interrupção de chamada que começou.

`processar_mensagem` retorna (`tratado_rapido`, `resposta`); o worker converte para texto, consulta `current_task().state` e usa `UiEvent("error", ...)` se o snapshot estiver `failed`, ou `UiEvent("reply", ...)` nos outros casos. Exceções viram evento de erro, e `idle` é enviado no `finally`.

**Limites observados:**
- A checagem de geração ocorre **antes** de `processar_mensagem`; **não há checagem adicional após seu retorno antes de enfileirar `reply/error`**. Portanto, uma resposta de tarefa já iniciada pode chegar visualmente mesmo depois de clicar Desligado. É risco de resposta obsoleta, não prova de execução de nova tarefa após desligamento.
- O frontend trata explicitamente apenas `state=="failed"` como erro. Outros estados, inclusive resposta textual de cancelamento, podem aparecer como `reply`. Uma resposta visível **não garante** estado de tarefa COMPLETED.
- `_append` mantém conteúdo no widget `Text` enquanto a janela vive; **Desligado não limpa a transcrição visível**. O backend pode encerrar sessão/Harness sem apagar o conteúdo mostrado na GUI. Não prometer privacidade/limpeza só pelo estado do botão.

## 5. Confirmação segura pela GUI

[`GuiConfirmationChannel`](../../ui/backend.py) recebe `ConfirmationRequest` da política de autorização: nome da tool, ação, motivo e orçamento de ações. Em `confirmar` cria `ConfirmationChoice`, publica `UiEvent("confirm")` e aguarda `Event.wait(timeout=45.0)`. Sem resposta, responde **False** e informa expiração; `finally` desfaz o registro de pendência e emite `confirm_done`.

O frontend cria um `tk.Toplevel` modal (`grab_set`) com texto da ação, justificativa e botões **Negar** / **Autorizar**; fechar o modal nega. Desligar/fechar a janela chama `deny_pending()`. Um `ConfirmationChoice.answer` é efetivamente idempotente: a primeira decisão marca `decided`, decisões posteriores não a sobrescrevem.

O frontend `_confirm` nega um pedido novo se estiver `closing`, `off` ou se já estiver decidido. **Standby não nega automaticamente uma confirmação que surgiu durante uma tarefa** (a função só bloqueia `off`/`closing`). Portanto, Standby não suspende solicitações de permissão.

A GUI é **apenas o canal de decisão**. Não escolhe `AUTO/CONFIRM/BLOCKED` e não executa ações diretamente; consulte [PermissionManager](../../core/permission_manager.py). A verificação de alvo/argumentos e demais limites permanecem no Dispatcher e na política. Timeout, recusa e fechamento do modal não transformam BLOCKED em autorizado.

## 6. Desligamento, cancelamento e recursos

- `worker.go_off()` invalida geração e bloqueia novos submits; chama `cancel_current()` (nega confirmação pendente e solicita `harness.cancel_current_task()` quando existir), depois enfileira operação `off`.
- `worker.close()` marca `_closing`, invalida geração, solicita cancelamento e enfileira `quit`. `AurenDesktop.close()` põe a GUI em `closing`, nega modal e chama `worker.close()`.
- No worker, `_dispose_harness()` tenta finalizar `_background_queue.shutdown(cancel_pending=False)`, `harness.fechar()` e `harness._encerrar_sessao_chat("closed")`, emitindo `notice` se alguma etapa falha. O `finally` da thread faz a mesma limpeza e envia `closed`.

O frontend só destrói a janela quando recebe `closed` durante `closing` ou quando detecta `worker.alive==False`; não chama `thread.join` bloqueante na thread Tk. **Isso não significa que o encerramento seja imediato**: a execução da tarefa é sequencial, e `quit/off` é consumido quando o worker volta a processar a fila. Se uma operação externa travar, o backend pode não alcançar o comando; `cancel_current_task` só sinaliza cancelamento cooperativo, não termina processos externos e não desfaz ações.

A fila de estratégias em background recebe `shutdown(cancel_pending=False)` no descarte. A finalização do Harness passa ainda por `fechar` e pelo método privado `_encerrar_sessao_chat`; isso cria **acoplamento explícito a detalhe interno** do Harness que merece teste de compatibilidade caso o ciclo de vida seja refatorado. Não inventar garantia de flush transacional de todas as tarefas e escritas.

## 7. Testes existentes e alcance real

| Fonte | O que verifica | O que **não** prova |
| --- | --- | --- |
| [`tests/test_desktop_ui_backend.py`](../../tests/test_desktop_ui_backend.py) | Confirmação explícita, timeout que nega e publica eventos, lazy Harness, reaproveitamento enquanto ligado, descarte ao desligar, nova instância após religar, só um caminho de execução, **compilação sintática** de `interface_auren.py` | Abrir widget com `tk.Tk()` real, layout, clique em botões, confirmação modal física, fluidez ou fechamento sob bloqueio real |
| [`tests/test_confirmation.py`](../../tests/test_confirmation.py) | Contrato de confirmação e classificação em fluxo simulado | Segurança de todos os efeitos reais de uma ferramenta após autorização |
| [`tests/test_cancellation_harness.py`](../../tests/test_cancellation_harness.py), [`tests/test_task_manager.py`](../../tests/test_task_manager.py) | Cancelamento, estados e pontos de checagem do Harness | Interrupção forçada de ferramentas/serviços externos travados |
| [`tests/test_scripts_layout.py`](../../tests/test_scripts_layout.py) | Existência e caminho dos atalhos de inicialização | Execução bem-sucedida de Tkinter em Windows configurado |
| [`tests/test_routing_single_owner.py`](../../tests/test_routing_single_owner.py) | Ausência de segundo dono da decisão/execução | Qualidade da resposta do modelo em ambiente Live |

**Natureza da evidência:** os testes e o código foram **lidos** nesta auditoria. No primeiro HEAD revisado da PR #127 (`0a3f24fa884e2531ba38544852ad4cf385d4e48e`), o [CI Linux completo](https://github.com/Yamatosemj/aurenOFC/actions/runs/38097470177) aprovou **556 passed/24 skipped** e o [CI focado Linux/Windows](https://github.com/Yamatosemj/aurenOFC/actions/runs/38097470147) aprovou Linux **166 passed/15 skipped**, Windows **181 passed** e modo seguro **110 passed** por plataforma. O **SHA final da PR deve ter CI próprio concluído antes do merge**. Os testes no Windows do CI hospedado não são, por si, um teste de janela Tk real, interação visual, API paga ou execução no notebook pessoal.

## 8. Backlog documental/operacional para PRs separadas

1. **Standby não é pausa do backend:** esclarecer semântica desejada para tarefa/confirmacão em execução e submit por outras fontes antes de alterar código.
2. **Resposta antiga após Desligado:** reproduzir ordenação de `reply/error/idle/off` com tarefa longa e transição de geração; decidir se a GUI deve ocultar output obsoleto.
3. **Cancelamento e fechamento:** testar tarefa externa demorada e evento `close`. Evitar prometer deadline de encerramento e confirmar o comportamento de limpeza de recursos/sessão.
4. **Confirmações e concorrência:** garantir no Windows físico que modal de 45 s, nova confirmação, Standby, Desligado e fechamento não resultam em autorizações indevidas nem modais presos.
5. **Retenção visual de conversa:** definir política de limpeza/privacidade quando desligar, reabrir ou mudar modo; o widget não é banco nem exclusão de memória persistente.
6. **Acoplamento com métodos privados do Harness:** avaliar contrato estável de teardown e fila de background em tarefa de runtime futura.
7. **Acessibilidade/UI real:** janela, DPI, fontes, teclado, Enter, foco, configurações de tema e múltiplos monitores permanecem sem validação física.

Não corrigir esses itens nesta PR exclusivamente Markdown. Testes Live/ações no PC e uso de modelo real exigem etapa e autorização separadas.

## 9. Checklist de manutenção

1. Ler [README](../../README.md), [AGENTS](../../AGENTS.md), [inventário](../INVENTARIO.md), [estado oficial](../../AUREN_STATE.md), documentação de [núcleo](01-nucleo.md), [segurança](02-roteamento-seguranca.md) e [sessão](03-modelo-sessao-memoria.md).
2. Rastrear `interface_auren.py` → `AurenUiWorker.submit`/`UiEvent` → `auren.criar_harness(confirmation_channel=...)` → `harness.processar_mensagem` → Dispatcher → ToolResult → UI.
3. Em mudanças dos estados, testar a **UI e o worker** separadamente: `mode`, `busy`, `_enabled`, `_generation`, `_closing` e `TaskState` não são sinônimos.
4. Em confirmações, preservar fail-closed, expiração, negação de modal, autorização única e impossibilidade de bypass da política por frontend.
5. Em cancelamento, diferenciar flag cooperativa, descarte enfileirado, fechamento de sessão e operação já iniciada. Não introduzir execução de tool na thread Tk.
6. Registrar CI por SHA final e classificar separadamente sintaxe, mock de backend, janela Windows real e efeitos Live. Não iniciar hardware, rede/API ou desktop pessoal para validar uma PR documental.
7. Qualquer alteração de produção futura: atualizar este documento e os testes da mesma área, em PR própria.

**Próxima área documental:** Etapa 8 — skills, recursos experimentais e extensibilidade, em PR separada.
