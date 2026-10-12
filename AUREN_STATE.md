# Auren — Estado operacional

> **Leia este arquivo primeiro em toda nova conversa ou tarefa de manutenção.** Este documento descreve o **estado corrente verificado**, não um diário de PRs. Confirme as afirmações dinâmicas com a `main`, as PRs abertas e os checks atuais no GitHub antes de agir.
>
> **Revisão de base:** 2026-10-10 · `main` consultada em `c18d58a88e2623818ccda1f08af6077c961598a1` (merge da [PR #130](https://github.com/Yamatosemj/aurenOFC/pull/130)). **O SHA de base não é promessa de HEAD atual.** O histórico integral foi arquivado, e a consolidação foi feita em PR documental separada.
>
> **Fontes:** [README](README.md) · [Regras para agentes](AGENTS.md) · [Inventário e estado por subsistema](docs/INVENTARIO.md) · [Histórico integral anterior à consolidação](docs/history/AUREN_STATE_SNAPSHOT_2026-10-10.md).

## 1. Situação e trabalho em foco

- **Projeto:** Auren, assistente pessoal para desktop/voz no Windows, escrito em Python; o proprietário quer evolução por **uma tarefa/PR de cada vez**, com mudanças e testes rastreáveis no GitHub.
- **Versão técnica configurada:** **V47** em [`config.py`](config.py), modelo padrão `gpt-5.6-luna`. O código de voz candidato à **V48** foi integrado pela [PR #119](https://github.com/Yamatosemj/aurenOFC/pull/119), **sem validação física de microfone/PTT/latência**. Não promover V48 a versão estável por decisão documental.
- **Documentação:** inventário inicial **Etapas 0–10 auditado estaticamente**, com referências em [`docs/architecture/`](docs/architecture/01-nucleo.md) e [`docs/INVENTARIO.md`](docs/INVENTARIO.md). Isso **não** comprova funcionamento Live nem encerra o desenvolvimento do Auren.
- **Manutenção em foco (PR candidata):** correção de roteamento/continuidade do incidente real de 2026-10-12: `abra a Steam` selecionou apenas ferramentas de janelas, `sim` perdeu o objetivo original e uma listagem foi tratada como conclusão. Branch `fix/steam-routing-followup-20261012`; nenhuma execução Live no Windows nem merge da correção comprovado. Preservar revisão de intenção, Dispatcher, contratos e permissões.

- **Verificação de intenção integrada na PR #132:** o mesmo modelo pode revisar ações mutáveis antes do Dispatcher (aprovar, esclarecer ou bloquear); falhas impedem a execução. **Otimização integrada na PR #133:** a segunda chamada fica dispensada somente quando uma proposta curta bate exatamente com o pedido explícito, incluindo ferramenta, argumentos e ausência de passos extras. Qualquer desvio, composição ou ambiguidade mantém a revisão por IA. Permissões e evidências pós-execução continuam independentes.

- **Interface Chrome local (candidata ao uso real):** `ui/chrome_server.py`, `ui/chrome.html` e `scripts/iniciar/AUREN_CHROME.bat` oferecem entrada web em 127.0.0.1, orbe WebGL original com Three.js local (MIT) e texto pelo mesmo `AurenUiWorker`. A PR #136 integrada removeu a seleção manual: mensagem acorda, 120 s sem atividade entram em Standby, `sair` desliga a sessão (sem matar o servidor), mensagem posterior inicia nova sessão. Confirmações continuam pelo canal seguro; GUI Tkinter preservada. O usuário relatou teste real bem-sucedido do orbe e de comandos do Chrome em 2026-10-11, mas a nova lógica de estados ainda exige validação no Chrome pessoal. Sem voz/web mobile ou lembretes reais.

## 2. Implementado no repositório — não confundir com validado

| Área | Estado verificável na revisão | Documento |
| --- | --- | --- |
| Núcleo, Router, ferramentas e segurança | Harness → Router → Dispatcher → contrato → PermissionManager → ferramenta → ToolResult; testes e guardas, sem segundo executor na GUI/voz | [01](docs/architecture/01-nucleo.md), [02](docs/architecture/02-roteamento-seguranca.md) |
| Modelo, sessão e memória | Provider OpenAI, contexto de sessão e memória SQLite; modelo default fixo e limites do cache | [03](docs/architecture/03-modelo-sessao-memoria.md) |
| Windows, arquivos, visão e navegador | Ferramentas registradas com permissões; operações dependentes do estado real do Windows/Playwright | [04](docs/architecture/04-windows-arquivos-visao.md), [05](docs/architecture/05-navegador-browser-intelligence.md) |
| Voz e interface | PTT e STT/TTS locais **candidatos**, Tkinter textual com estados Ativo/Standby/Desligado; **hardware/GUI física não validados nesta fase** | [06](docs/architecture/06-voz-stt-tts.md), [07](docs/architecture/07-interface-desktop-gui.md) |
| Extensibilidade | Carregador de skills, catálogo de capacidades e experimento de áudio opt-in; wake word fora do runtime | [08](docs/architecture/08-skills-capacidades-extensibilidade.md) |
| Testes, inicialização e instalação | CI hospedado; controle remoto autorizado separadamente; launchers Python e instaladores por código-fonte | [09](docs/architecture/09-testes-ci-controle-remoto.md), [10](docs/architecture/10-entradas-config-instalacao-distribuicao.md) |

**Números são snapshots:** o [inventário](docs/INVENTARIO.md) registrou 49 ferramentas e 14 capacidades declarativas. Contar novamente no registry se houver mudança; não tratar a lista declarativa como ferramenta executável.

**Bloqueio Live identificado no teste da PR #138 (2026-10-12):** o log real mostrou erro HTTP 400 da Responses API ate para `ola auren`: `clicar_mouse_windows` tinha `strict=True` mas `coordinate_space`/`vision_snapshot_id` estavam fora de `required`. A revisao do registry encontrou o mesmo problema em `arrastar_mouse_windows`. Na branch, as duas tools passaram a `strict=False` somente para preservar parametros opcionais; contratos, Dispatcher e permissoes locais permanecem obrigatorios. Teste de regressao novo: `tests/test_tool_schema_api_compat.py` (inspeciona as 49 tools e simula payload do provider sem custo). **A correção aguarda CI do HEAD final e novo teste real da API no Windows; nao declarar a PR validada Live.**

**Segundo teste Live na PR #138 (2026-10-12):** `ola auren` voltou a responder e `abra a steam` usou corretamente `abrir_programa`; reabertura também funcionou. O teste expôs outra falha no mesmo fluxo: `feche a steam porcompleto` executou apenas `listar_janelas_windows` e marcou `TASK_LOCAL_COMPLETION` sem fechar nada. Causa estática: `_parece_tarefa_de_acao` ignorava o imperativo `feche`. Outra falha: `fechar_janela_windows` retorna somente solicitação `WM_CLOSE`, mas o modelo declarou conclusão sem evidência. A branch inclui ajuste de verbos, roteamento de fechamento completo para processos, e guard do Harness exigindo evidência posterior de ausência de janela/processo antes de relatar sucesso; a política de confirmação para `encerrar_processo_windows` permanece intacta. Novos testes simulados em `tests/test_close_intent_verification.py`. CI do HEAD final e novo teste Live deste caso ainda pendentes.

**Revisão do incidente Steam (branch, ainda não integrado):** `core/router.py` agora extrai `Objetivo original` da entrada montada pelo Harness para selecionar ferramentas sem se contaminar por instruções ou resultados; comandos simples de abrir aplicativos incluem `abrir_programa`. `core/harness_followup.py` e o Harness guardam por uma única mensagem o objetivo de uma pergunta pendente; `sim` retoma o objetivo e `não` cancela sem ferramenta. Respostas soltas sem pendência não viram ações. `core/harness_cycle.py` captura perguntas após consulta e o revisor também pode registrar esclarecimentos. Heurística bloqueia conclusão por leitura com objetivo `sim`. Testes sintéticos novos: `tests/test_steam_routing_followup.py`. Verificar CI/pytest do HEAD final; nenhuma afirmação de sucesso Live.

## 3. Evidências confirmadas e o que NÃO foi testado

- **Última etapa documental integrada antes desta consolidação:** [PR #130](https://github.com/Yamatosemj/aurenOFC/pull/130), merge `c18d58a88e2623818ccda1f08af6077c961598a1`. No **HEAD final da PR**, o [CI Linux completo](https://github.com/Yamatosemj/aurenOFC/actions/runs/38099193036) aprovou **556 passed / 24 skipped**; o [CI focado Linux/Windows hospedados](https://github.com/Yamatosemj/aurenOFC/actions/runs/38099192874) aprovou **166 passed / 15 skipped** no Linux, **181 passed** no Windows, e **110 passed** em modo seguro por sistema.
- **Pytest remoto no Windows pessoal realmente ocorreu:** [PR #119, run #38085000162](https://github.com/Yamatosemj/aurenOFC/actions/runs/38085000162), pedido por comentário com SHA verificado, **579 passed, 1 skipped, 1 warning e exit=0** na ocasião. **Não prova que o runner esteja online agora.**
- **Não comprovado por essas evidências:** PTT/microfone físico, STT/TTS reais e latência ponta a ponta; janela Tk/fluxo de cliques físicos; instalação limpa/release portátil; navegação/modelo e automação Live atuais; todas as camadas L4/L5 ou qualidade geral do assistente. Runners `windows-latest` do GitHub **não são o notebook pessoal**.
- **Segurança remota:** o `before-job.ps1`, aprovações e botão de emergência residem **fora do repositório**, no Windows; não inferir a situação deles apenas pelo GitHub. Testes no PC e Live/API exigem permissão expressa, revisão do SHA e as proteções vigentes. Veja [guia remoto](docs/CONTROLE_REMOTO_GITHUB.md) e [matriz de testes](docs/architecture/09-testes-ci-controle-remoto.md).

## 4. Pendências conhecidas — candidatas, NÃO tarefas já aprovadas

1. **Validar uso real antes de elevar status:** PTT, ASR, TTS, GUI, browser e modelo por testes pequenos, controlados e autorizados no Windows. Não executar automaticamente scripts Live ou ações que consumam API.
2. **Bootstrap/instalação:** atalho GUI ignora `.venv`; voz e instalação escolhem Python de formas diferentes; instaladores não criam `.venv`; Chromium do Playwright não vem automaticamente com o pacote Python.
3. **Instalador de voz:** remove todo diretório de cache ASR se presente, embora anuncie limpeza de cache incompleto; corrigir e validar sem apagar modelo do usuário indevidamente.
4. **Modelo configurável:** `AUREN_MODEL` é lido por `config.py`, porém um override diferente do default gera incoerência com literais de `auren.py`; identidade no prompt também é fixa.
5. **Interface:** Standby bloqueia envio na janela, mas não pausa worker; uma resposta de tarefa iniciada pode chegar após Desligado. Precisam de reprodução e decisão sobre UX, não de alteração silenciosa.
6. **Skills/experimentos:** instalação de skills não valida explicitamente nomes/caminhos/symlinks; revisar antes de usar fontes não confiáveis. Avaliar fallback após efeitos parciais no experimento de áudio.
7. **Branches antigas:** existem PRs históricas ainda abertas (incluindo cadeias antigas de voz, plugins, memória e arquivos). **Não assumir que representem o trabalho ativo nem mesclá-las cegamente**. Conferir contra `main`, dependências e segurança primeiro.

O backlog antigo de ideias (multi-device, HUD, ESP32, wake word, memória avançada etc.) permanece **histórico**, não autorização de implementação: [snapshot anterior](docs/history/AUREN_STATE_SNAPSHOT_2026-10-10.md). A prioridade seguinte deve ser decidida com o proprietário, uma por vez.

## 5. Procedimento obrigatório para manter o estado confiável

1. **Antes de mexer:** ler `README.md`, `AGENTS.md`, este arquivo e o documento técnico relevante; buscar `main` atual, PRs abertas e checks, sem confiar em SHA ou status escrito anteriormente.
2. **Escolher uma tarefa concreta**, branch/PR focalizada e critérios de aceitação. Para achados fora do escopo, registrar pendência, **não implementar** sem autorização.
3. **Preservar o caminho único** Router → Dispatcher → contrato → permissão → ferramenta → ToolResult; dados externos/skills não podem autorizar ferramentas. Sem `shell=True`, `eval` ou `exec` em novas implementações.
4. **Validar no SHA efetivo** e distinguir teste sintético, CI Linux/Windows hospedado, pytest do runner pessoal e Live/API. Fazer alterações no runner, ações reais no PC ou acesso à API somente quando autorizados.
5. **Atualizar este arquivo na mesma PR de mudança:** alterar só situação vigente, limitações e evidência verificável; **não anexar um novo diário inteiro**. Registrar marcos históricos relevantes em documento separado ou PR, sem mover fatos antigos para “estado atual”.
6. **Antes do merge:** revisar diff, checar links relativos e CI do último commit. A descrição da PR pode registrar runs do HEAD final **sem produzir commit recursivo só para anexar os mesmos resultados**. Depois do merge, confirmar SHA integrado e não declarar uma fase seguinte iniciada sem pedido.

### Histórico e fonte de verdade

- [Snapshot integral de 2026-10-10](docs/history/AUREN_STATE_SNAPSHOT_2026-10-10.md) — cópia preservada do antigo `AUREN_STATE.md`; contém diagnósticos, PRs e instruções antigas **superadas** por verificações posteriores.
- [Inventário e PRs documentais 0–10](docs/INVENTARIO.md) — mapa e referências de todas as auditorias estáticas.
- [Guia dos testes por GitHub](docs/TESTES_GITHUB.md) — histórico e procedimentos do controle remoto; **estado local atual requer confirmação**.

**Regra final:** *o estado curto orienta a próxima decisão; o código, o GitHub e o ambiente de teste autorizados determinam o que é verdade agora.*
