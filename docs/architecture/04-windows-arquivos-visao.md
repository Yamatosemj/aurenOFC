# Arquitetura 04 — Windows, arquivos e visão

> **Etapa 4:** auditoria estática sobre a `main` em `d0c9c991a3311127f59368d123020b2c065f1e1f`, em 2026-10-10. Documento para manutenção: o código e os testes são a referência final. **Nenhuma execução Live ou no Windows pessoal foi realizada nesta auditoria.**
>
> O [núcleo](01-nucleo.md) mantém o ciclo e a verificação posterior. O [caminho de ferramentas](02-roteamento-seguranca.md) valida argumentos e autoriza ações. Aqui estão as implementações Windows, a leitura local de arquivos e a conversão de coordenadas visuais. **Uma ferramenta registrada não implica que seu uso físico esteja validado.**

## 1. Mapa e limites da responsabilidade

| Fonte | Responsabilidade verificada |
| --- | --- |
| [tools/windows.py](../../tools/windows.py) | Fachada de compatibilidade: reexporta funções distribuídas em módulos Windows; também configura Win32 para chamadas legadas |
| [tools/windows_window.py](../../tools/windows_window.py) | Enumerar, identificar, focar, minimizar, maximizar, geometria, mover, redimensionar, restaurar e solicitar fechamento de janelas |
| [tools/windows_uia.py](../../tools/windows_uia.py) | Inspeção e atuação em controles de UI Automation via Windows PowerShell / UIAutomationClient |
| [tools/windows_input.py](../../tools/windows_input.py) | Teclas globais, cursor, clique, arraste, teclas de mídia e limites da área de trabalho virtual / DPI |
| [tools/windows_media.py](../../tools/windows_media.py) | Pausa explícita de sessão GSMTC única, com leitura de estado antes e depois |
| [tools/windows_screenshot.py](../../tools/windows_screenshot.py) | Screenshot de todos os monitores com Pillow e metadados físicos |
| [tools/windows_processes.py](../../tools/windows_processes.py) | Listar processos e solicitar encerramento com `taskkill` e filtros de proteção |
| [tools/windows_audio.py](../../tools/windows_audio.py) | Ler e alterar áudio por API de endpoint Core Audio/COM |
| [tools/windows_clipboard.py](../../tools/windows_clipboard.py) | Clipboard Unicode pela Win32, com assinaturas de handles/pointers |
| [tools/windows_system.py](../../tools/windows_system.py) | Leitura do estado da máquina |
| [tools/applications.py](../../tools/applications.py) | Descobrir e abrir aplicativos do Start Menu, atalhos, executáveis e PATH |
| [tools/files.py](../../tools/files.py) | Busca por nome, extensão e data nas pastas locais comuns e OneDrive, até dez resultados |
| [tools/file_intelligence.py](../../tools/file_intelligence.py) | Inspecionar metadados/origem/cópias e ler texto com controles de caminho |
| [core/vision.py](../../core/vision.py) | Preparar imagem para o modelo, associar snapshot à tarefa e converter pontos para coordenadas Windows |
| [tools/dispatcher.py](../../tools/dispatcher.py) | Único registro de handlers, validação, transformação visual, preflight UIA e autorização |
| [core/permission_manager.py](../../core/permission_manager.py) | Política AUTO/CONFIRM/BLOCKED, classificação por ação e barreiras de caminho |
| [core/harness_guards.py](../../core/harness_guards.py) | Evita conclusão positiva de ação visual composta sem reobservação exigida |

O registry atual tem **49 ferramentas**. Esta área **não** adiciona ferramentas, não cria executor paralelo e **não** incorpora recursos de escrita de arquivos/undo que não constam em [core/tools_registry.py](../../core/tools_registry.py) e no Dispatcher da `main`.

### Pausa de mídia local verificável (primeira entrega, 26/11/2026)

`controle_midia_windows` com `acao="pausar"` preserva o Dispatcher, contrato e `windows.audio.control` do PermissionManager. `tools/windows_input.py` delega essa ação a `tools/windows_media.py`; as outras ações de mídia continuam legadas. O executor usa `GlobalSystemMediaTransportControlsSessionManager.get_sessions()`, sem escolher automaticamente `get_current_session()`. Com mais de uma sessão em reprodução, recusa o destino. Uma sessão em reprodução pode coexistir com sessões pausadas; sessões em transição ou com estado ilegível impedem a seleção. Sem sessão em reprodução, uma única sessão pausada resulta em `ja_pausada` sem comando; múltiplas sessões pausadas são ambíguas.

Na sessão selecionada, o executor relê o estado e `is_pause_enabled` imediatamente antes de chamar **somente** `try_pause_async()`. Depois consulta `get_playback_info()` na mesma instância por um prazo curto. `ToolResult.data.estado` distingue `pausa_confirmada` (`ok=True`, antes reproduzindo/depois pausado), `ja_pausada` (`ok=True`, nenhum comando), `falha` (`ok=False`, ausência, ambiguidade, indisponibilidade ou recusa) e `desconhecido` (`ok=False`, leitura incerta, erro após a tentativa ou ausência de confirmação). O booleano retornado por `try_pause_async()` sozinho não é tratado como comprovação do estado final. O ID do aplicativo, quando disponível, é metadado de diagnóstico; não é usado como identidade única da sessão.

Não há fallback para `VK_MEDIA_PLAY_PAUSE`. Após uma tentativa `pausar`, o PermissionManager bloqueia `play_pause` durante a mesma tarefa, inclusive após checkpoint/retomada; nova tarefa reinicia essa trava. O caminho experimental de áudio também encerra a tentativa de pausa com resposta de falha/estado incerto, sem abrir fallback do modelo. O roteamento normal ainda depende do modelo escolher `acao="pausar"`; o schema e o prompt explicitam essa escolha.

O backend requer Windows 10 1809 ou posterior e um player que publique sessão nos controles de mídia do Windows. É importado apenas ao executar a pausa, para manter importação segura em Linux. `requirements.txt` fixa `winrt-Windows.Media.Control` e `winrt-Windows.Media` somente no Windows. A compatibilidade de importação foi verificada em CPython 3.13 no Windows com PyWinRT 4!10.0.28000.2957 e runtime resolvido 4.2.1; não houve chamada ao gerenciador real. A licença declarada do PyWinRT é MIT. [API GSMTC](https://learn.microsoft.com/en-us/uwp/api/windows.media.control.globalsystemmediatransportcontrolssessionmanager?view=winrt-26100) · [TryPauseAsync](https://learn.microsoft.com/en-us/uwp/api/windows.media.control.globalsystemmediatransportcontrolssession.trypauseasync?view=winrt-26100) · [pacote PyPI](https://pypi.org/project/winrt-Windows.Media.Control/).

**Limites residuais:** o estado verificado é o publicado pelo player ao Windows, não prova áudio audível; cobertura de Spotify, navegadores e outros players, permissão `globalMediaControl` para o processo Python sem empacotamento, tempo de resposta e comportamento real de WinRT no PC do proprietário aguardam teste supervisionado. O backend não distingue música de vídeo quando o player não informa o tipo. Uma nova sessão pode surgir entre a enumeração e o comando; a pausa continua vinculada ao objeto inicialmente escolhido. Não houve teste Live, hardware ou chamada paga.

Fluxo de execução:

```text
Harness / modelo
  → Router seleciona a ferramenta
  → Dispatcher verifica JSON e ToolContract
  → [clique/arraste visual: transforma e valida snapshot]
  → [preencher UIA: resolve controle antes da autorização]
  → PermissionManager classifica/autoriza
  → handler Windows / arquivos
  → ToolResult normalizado
  → Harness registra, reobserva se necessário e decide conclusão
```

## 2. Windows: janelas, processos e aplicativos

### 2.1. Identificação e controle de janelas

[windows_window.py](../../tools/windows_window.py) enumera HWNDs e títulos. A busca prioriza título exato, correspondência parcial, executável do processo e, depois, similaridade de nome com limiar de **0,78**; inclui tratamento especial para Explorer e busca tardia de janelas minimizadas. Janelas ativas ganham preferência em algumas correspondências. Isso é **heurística de alvo**, não identidade infalível.

O cache associa nome normalizado a HWND e processo. Antes de reutilizá-lo, tenta verificar que a janela continua válida, que o processo corresponde e que existe título atual. **Não garante que duas janelas do mesmo aplicativo tenham sido distinguidas como o usuário queria.**

`listar_janelas_windows` e `obter_geometria_janela_windows` só observam; `focar`, `minimizar`, `maximizar`, `mover`, `redimensionar` e `restaurar` integram a allowlist de controles reversíveis AUTO. `fechar_janela_windows` usa `PostMessageW(WM_CLOSE)`: retorna que **solicitou** o fechamento, não comprova que o aplicativo encerrou ou salvou; requer confirmação pelo PermissionManager. Mover/redimensionar validam limites próprios, mas não garantem layout final da aplicação.

### 2.2. Processos, status, áudio e clipboard

- [windows_processes.py](../../tools/windows_processes.py) lista processos via ferramentas do Windows e usa `taskkill` para encerramento. **Correção candidata do achado 9:** a lista de imagens do sistema passou a ser única em [windows_process_policy.py](../../tools/windows_process_policy.py) para `/IM`, `/PID` comum e `/F`, fechando a divergência que deixava alguns nomes (como `svchost.exe` e `taskhostw.exe`) protegidos só no modo forçado. PID continua exigindo identificação real do executável; se o usuário/modelo fornecer também um nome no modo comum, ele deve coincidir com a imagem identificada. Valores booleanos não são aceitos como PID. O modo `/F` mantém exigência de PID + nome exato + caminho absoluto verificável, bloqueio de executáveis sob a pasta Windows, confirmação explícita e retorno como **solicitação enviada, nunca encerramento comprovado**. **Uma lista negativa de nomes não é exaustiva**, a identidade pode mudar entre consulta e encerramento, e nenhuma execução real de `taskkill`/`/F` foi feita. Testes isolados estão em [test_windows_process_safety_consistency.py](../../tests/test_windows_process_safety_consistency.py).
- [windows_system.py](../../tools/windows_system.py) e [windows_audio.py](../../tools/windows_audio.py) expõem leitura/controle locais. Áudio usa endpoint COM; ambiente sem Windows/API pode falhar normalmente.
- [windows_clipboard.py](../../tools/windows_clipboard.py) usa `CF_UNICODETEXT`, `OpenClipboard`, funções de memória global e fechamento. A ferramenta é leitura/escrita de **texto**, não gerenciador de histórico de clipboard; uma correção anterior de assinaturas ctypes não substitui validação de uso real em toda configuração.
- [applications.py](../../tools/applications.py) tenta `Get-StartApps`, pesquisa recursiva de atalhos `.lnk`, executáveis em diretórios usuais e `shutil.which`. Há timeouts nas buscas PowerShell; achar nome semelhante ou iniciar processo **não assegura que a janela esperada esteja pronta**. Pedidos com alvo anafórico ambíguo são recusados nesse módulo.

### 2.3. UI Automation não é clique por imagem

[windows_uia.py](../../tools/windows_uia.py) acessa árvore de controles pela automação do Windows, usando script temporário PowerShell executado com `-STA` e limite de **20 s**. A inspeção devolve nome, tipo, AutomationId, estados e padrões; mostra até **80 controles**, conforme limite do wrapper. As ações disponíveis são `clicar_elemento_windows`, `preencher_elemento_windows`, `alternar_elemento_windows` e `selecionar_elemento_windows`.

O Dispatcher resolve previamente o controle para `preencher_elemento_windows`. Se a resolução direta falhar, pode inspecionar a árvore e aceitar apenas correspondência exata única por nome/AutomationId; ambiguidade falha **antes da autorização**. Para controles protegidos, usa o AutomationId ou nome resolvido na busca de execução. A política classifica o preenchimento com base no tipo de campo, alvo e conteúdo; UIA de clique/toggle/seleção exige confirmação, não é AUTO indiscriminado.

**S06 — identidade no preenchimento:** o preflight registra HWND, RuntimeId, nome, AutomationId, tipo e IsPassword. Sem RuntimeId, o preenchimento é recusado antes da autorização; isso não cria uma confirmação extra. Após a decisão do usuário, a execução confere o HWND e lê os atributos atuais do AutomationElement novamente selecionado antes de foco ou escrita; os atributos guardados na enumeração não servem como prova atual. Uma troca de instância ou de atributos é recusada, inclusive quando outra instância reutiliza nome ou AutomationId. A confirmação concedida para um campo protegido não autoriza outro campo. A checagem IsPassword e a negação do usuário permanecem. Leituras de verificação e foco do fallback também usam a identidade esperada. Após a entrada alternativa, divergência ou ausência de controle verificável é reportada como falha, mesmo que o efeito já possa ter ocorrido; não repetir automaticamente o preenchimento. Clique, alternância e seleção UIA não foram modificados nesta correção.

No fallback de digitação protegida, o script exige janela em primeiro plano, clique físico e controle focado antes de enviar eventos; a confirmação de valor de senha pode ser **indireta** porque `PasswordBox` não expõe leitura do conteúdo. Não declarar que o valor secreto foi comparado byte a byte. Para campos comuns, a tentativa de confirmação utiliza novamente o controle.

**Limites:** provedores UIA podem omitir controles/padrões, expor estados atrasados, falhar por privilégio ou mudar durante a operação. O RuntimeId só é garantido como único na interface do desktop em que foi gerado e [pode ser reutilizado com o tempo](https://learn.microsoft.com/en-us/dotnet/api/system.windows.automation.automationelement.getruntimeid?view=windowsdesktop-10.0); HWND também pode ser reutilizado. A checagem não torna atômica a autorização e o efeito nem elimina mudanças de foco entre verificações. Os testes S06 usam controles sintéticos e efeitos simulados; estabilidade de RuntimeId entre processos PowerShell, provedores reais, fallback físico e impacto em interfaces legítimas ainda exigem validação supervisionada no Windows. A confirmação humana e o preflight não demonstram semântica real de toda interface. Não usar UIA como autorização para burlar proteções da aplicação.

## 3. Arquivos: busca, inspeção e leitura

### 3.1. São três ferramentas diferentes

| Ferramenta | Observação real | Não promete |
| --- | --- | --- |
| `buscar_arquivo` ([files.py](../../tools/files.py)) | Varre Downloads/Desktop/Documents e variantes OneDrive existentes; filtra nome/termos, extensões e `hoje`/`ontem`/`semana`; ordena pontuação e data de modificação; mostra até 10 | Buscar todo o disco, ler conteúdo, encontrar semanticamente qualquer documento |
| `inspecionar_arquivo` ([file_intelligence.py](../../tools/file_intelligence.py)) | Metadados, acessibilidade, tipo por extensão/assinatura, SHA-256, datas, indício `Zone.Identifier` e cópias de mesmo hash em raízes específicas | Descobrir autor/download/origem histórica completa ou provar cadeia de custódia |
| `ler_arquivo` ([file_intelligence.py](../../tools/file_intelligence.py)) | Lê texto `.txt`, `.md`, `.json` e `.csv`; detecta encoding e retorna trecho/continuação | Extrair PDF, DOCX, XLSX, imagem, OCR ou modificar arquivos |

A inspeção pode reconhecer a assinatura de PDF/ZIP/imagem, **sem extrair o conteúdo**. Origem `HostUrl`/`ReferrerUrl` só é evidência quando a stream `Zone.Identifier` está disponível; ausência permanece **desconhecida**. Busca por cópias usa SHA-256 e mesmo tamanho, com teto de **20.000 arquivos examinados** e quantidade configurável de achados. Mesmo hash comprova bytes iguais, não que uma cópia veio da outra.

Leitura tem padrão de **12.000 caracteres**, máximo de **20.000** por chamada e deslocamento até **1.000.000 caracteres**. `proximo_inicio` sinaliza continuação. O retorno inclui `conteudo_nao_confiavel=True`. Erros de acesso, encoding, extensão e tamanho/offset têm códigos estruturados.

### 3.2. Permissões de caminho — duas camadas

[`_classify_read_path`](../../tools/file_intelligence.py) resolve o caminho antes da classificação:

1. **BLOCKED:** componentes sensíveis, como `AppData`, `.ssh`, `.aws` e perfis de navegador. O bloqueio se aplica mesmo dentro de uma raiz permitida; confirmação não libera.
2. **AUTO:** dentro de Downloads/Desktop/Documents/Documentos/Área de Trabalho do perfil, ou raízes OneDrive configuradas e resolvidas, se não estiver em caminho bloqueado.
3. **CONFIRM:** fora dessas raízes, com consentimento específico para o caminho resolvido.

O [Dispatcher](../../tools/dispatcher.py) resolve o destino antes de chamar o [PermissionManager](../../core/permission_manager.py), que classifica e, quando necessário, apresenta esse caminho canônico para confirmação. O Dispatcher só injeta `_caminho_confirmado` para o destino autorizado; ele e o handler recusam uma mudança de destino antes da leitura ou inspeção, inclusive para ações AUTO. O handler preserva o bloqueio de caminhos sensíveis. Testes cobrem `..`, symlink para fora da raiz, perfis de browser, recusa, troca simulada de destino e tentativa de contornar BLOCKED.

Na revisão S01 da [PR #188](https://github.com/Yamatosemj/aurenOFC/pull/188), o PermissionManager devolve ao Dispatcher o destino e a política **efetivamente classificados**, junto do nível autorizado. Se a resolução ou a identidade da política divergir do destino apresentado, a ação é negada antes da confirmação; uma classificação preliminar não cria comprovante de `CONFIRM`. Caso a política efetiva exija confirmação, o comprovante só é emitido após a decisão correspondente. A comparação também rejeita níveis de política desconhecidos ou uma classificação preliminar mais restritiva sem confirmação. Os testes usam somente arquivos sintéticos para leitura e inspeção.

**Limite residual:** a verificação do caminho e a abertura pelo sistema operacional não são atômicas. Se o sistema de arquivos mudar depois da última verificação, esta correção não comprova a identidade do arquivo aberto por um identificador de arquivo/handle; o cenário requer avaliação própria antes de prometer proteção contra essa janela.

**Observação:** isso não é sandbox de sistema operacional nem política global para toda possível operação de arquivos; é o comportamento das ferramentas de leitura/inspeção atuais. `buscar_arquivo` possui escopo de busca próprio, sem utilizar esse leitor de conteúdo.

## 4. Visão: imagem, geometria e ação

### 4.1. Captura e preparação

[capturar_tela_windows](../../tools/windows_screenshot.py) usa Pillow `ImageGrab.grab(all_screens=True)`; salva PNG em `runtime/screenshots/` e devolve o caminho, dimensões, origem e tamanho do desktop virtual, espaço de coordenadas e indicação do contexto de DPI por monitor. A captura de todas as telas pode conter informação sensível: o módulo não representa uma política de descarte ou expiração de screenshots.

[core/vision.py](../../core/vision.py) prepara `input_image` com limite padrão de **5 MB**. Quando necessário, tenta compressão PNG/JPEG e só então redução de tamanho; registra dimensões de origem, dimensões realmente enviadas, escala, compressão e redimensionamento. `prepare_vision_result_content` acrescenta metadados técnicos à imagem capturada e registra o snapshot ativo via `ContextVar`.

A transformação só é marcada `transformacao_segura=True` quando há ID de snapshot, consistência de origem, proporção compatível (tolerância relativa **1%**) e DPI `per_monitor` verificado. Uma imagem recebida pelo modelo **não garante**, sozinha, geometria apta a clicar.

### 4.2. Conversão antes da autorização

A conversão em [`transform_visual_tool_arguments`](../../core/vision.py) só se aplica a `clicar_mouse_windows` e `arrastar_mouse_windows`. Ela é acionada por `coordinate_space=vision_image` ou por ID de snapshot informado. São necessários ID igual ao ativo e geometria segura; imagem fora dos limites, proporção divergente, campos inválidos e snapshot antigo são rejeitados. A origem virtual pode ser negativa em multimonitor.

Em [executar_ferramenta](../../tools/dispatcher.py), argumentos e contrato são validados **antes** da conversão; coordenadas visuais são transformadas **antes** da classificação de permissão. O executor recebe pontos físicos do Windows e o ToolResult anexa `vision_coordinate_transform`, preservando a marca de conteúdo não confiável. Coordenadas Windows diretas, sem snapshot visual, não passam por essa conversão: continuam sujeitas às verificações do próprio mouse e à autorização.

[windows_input.py](../../tools/windows_input.py) confere limites virtuais antes de mover/clicar/arrastar. Arraste valida origem e destino e duração entre **50 e 3.000 ms**; eventos de liberação são protegidos por `finally` após iniciar o gesto. Isso não torna o clique semanticamente seguro: clicar no lugar certo da imagem pode continuar sendo a ação errada na aplicação.

### 4.3. O que conta como conclusão

O [guard do Harness](../../core/harness_guards.py) pode exigir **nova observação** após ação visual relevante, em vez de aceitar como sucesso apenas o retorno textual de clique/arraste. O limite de tentativas de verificação evita repetição infinita; sem evidência suficiente, deve haver encerramento com falha de verificação, não sucesso fictício.

Essa proteção é **verificação de estado observado**, não prova de que o sistema entendeu corretamente todos os efeitos colaterais da interface. Para testar de ponta a ponta, é indispensável Windows real, DPI/monitores representativos e ações expressamente autorizadas.

## 5. Matriz de política e falhas

| Classe | Regra principal | Exemplos de falha/limite |
| --- | --- | --- |
| Leitura Windows | AUTO por capacidade | Módulo Windows ausente, API indisponível, screenshot sem Pillow |
| Operações reversíveis de janela | AUTO quando na allowlist | Alvo heurístico errado, janela fechada entre identificação e execução |
| Fechar janela / processo | CONFIRM | `WM_CLOSE` enviado sem comprovação de encerramento; processo protegido |
| Teclado/mouse global | Movimento AUTO; clique/arraste e atalhos de risco CONFIRM | Fora da área virtual; snapshot desatualizado; ação sem progresso |
| UIA | Leitura AUTO; ações conforme tipo, alvo e risco | Preflight falha, alvo ambíguo, valor não confirmado, provedor inacessível |
| Leitura/inspeção de arquivo | AUTO nas raízes permitidas, CONFIRM fora, BLOCKED nos sensíveis | Symlink/`..` resolvidos, acesso negado, formato não suportado |
| Conteúdo externo retornado | Nunca é instrução do usuário | Leitura de arquivo aciona guarda de origem não confiável para ações seguintes contáveis |

A classificação exata pode depender de argumentos e estado da tarefa: **não copie o nível base do registry como se autorizasse qualquer ação**. Consulte [PermissionManager](../../core/permission_manager.py) e a [auditoria de política](02-roteamento-seguranca.md) antes de mudar um handler.

## 6. Evidências e testes — o que provam

| Arquivos de teste | Cobertura observada |
| --- | --- |
| [test_file_intelligence.py](../../tests/test_file_intelligence.py) | Hash/tipos/origem desconhecida, cópias sintéticas, leitura/offset, retorno não confiável, allowlist e confirmação/symlink |
| [test_vision_input.py](../../tests/test_vision_input.py) | Preparação multimodal, compressão, escala, origem negativa, dimensões e rejeição de proporção |
| [test_visual_coordinate_dispatcher_integration.py](../../tests/test_visual_coordinate_dispatcher_integration.py) | Imagem → Dispatcher → clique/arraste simulados, snapshot antigo, DPI não verificado, verificação posterior e preservação de proveniência |
| [test_visual_input.py](../../tests/test_visual_input.py) | Mouse/arraste com Win32 simulado, limites da tela virtual e contexto DPI |
| [test_windows_uia_module_boundary.py](../../tests/test_windows_uia_module_boundary.py) e [test_windows_*_module_boundary.py](../../tests/) | Limites modulares, imports e localização dos handlers; **não executam UI Automation física** |
| [test_permission_policy.py](../../tests/test_permission_policy.py), [test_execution_single_path.py](../../tests/test_execution_single_path.py), [test_prompt_injection.py](../../tests/test_prompt_injection.py) | Política, rota única e marcação/guarda de fontes externas em cenários controlados |

**Natureza da evidência:** os arquivos e suas expectativas foram lidos nesta revisão. A PR documental anterior #123 passou no CI hospedado, mas **seus resultados não aprovam automaticamente esta nova PR**. A PR #124 teve CI hospedado aprovado no primeiro HEAD `c80aaadefb49a3455dd1294fb914e78c59561bf2`: [Linux completo](https://github.com/Yamatosemj/aurenOFC/actions/runs/38095610847) (556 passed, 24 skipped) e [focados Linux/Windows](https://github.com/Yamatosemj/aurenOFC/actions/runs/38095610844) (Linux 166 passed/15 skipped, Windows 181 passed, testes seguros 110 em cada sistema). **O HEAD final deve ter checks próprios concluídos antes do merge.** Nenhuma captura, UIA, clipboard, API paga, clique, arraste ou inspeção do computador pessoal foi executada neste trabalho.

## 7. Lacunas para tarefas próprias

- **Precisão de alvos Windows:** nomes fuzzy, títulos repetidos e cache HWND não equivalem a uma identidade imutável; elaborar cenários reais de UIA/janelas antes de mudar algoritmo.
- **UIA protegido:** confirmação indireta de preenchimento de senha merece teste físico supervisionado; não tentar validar lendo segredos.
- **Persistência de screenshots:** verificar política de limpeza/retenção e exposição do diretório em tarefa separada, antes de afirmar privacidade integral.
- **Processos e aplicativos:** lista protegida e busca recursiva são regras atuais limitadas; custo da busca e cobertura de processos críticos devem ser medidos antes de refatoração.
- **Files:** ausência de mecanismo de operações/undo no registry atual; não confundir ideias de backlog com ferramenta implementada.
- **Cobertura:** CI com mocks e inspeção estática não demonstram automação segura e confiável com diferentes monitores, permissões, aplicativos e escala de DPI.

## 8. Checklist para manutenção

1. Ler `README.md`, `AUREN_STATE.md`, [inventário](../INVENTARIO.md), [núcleo](01-nucleo.md) e [roteamento](02-roteamento-seguranca.md).
2. Rastrear da definição em `core/tools_registry.py` até contrato, Dispatcher, PermissionManager, handler e consumidores no Harness; evitar executar função Windows por rota nova.
3. Para leitura de arquivo: resolver caminho, aplicar bloqueio e confirmação no **mesmo alvo efetivo**, preservar `ToolResult` não confiável e testar symlink/`..`.
4. Para UIA: testar alvo ambíguo, foco, campos protegidos, autorização e retorno não confirmado; nenhum segredo real nos testes.
5. Para visão: testar snapshot vigente/antigo, DPI, proporções, tela virtual com origem negativa, out-of-bounds, autorização e verificação após ação.
6. Distinguir testes simulados, CI hospedado, Windows pessoal e Live; **nenhum passa a representar o outro**.
7. Registrar mudança no estado oficial e adicionar testes de regressão em PR específica se futuramente houver alteração de runtime.

**Próxima área documental após esta PR:** navegador e Browser Intelligence (Etapa 5). Não implementar essa área nesta etapa.
