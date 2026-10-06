# Auren — Estado oficial do projeto

> **Este arquivo é a fonte de verdade operacional do Auren.**
> Antes de iniciar uma nova tarefa, consulte este arquivo e compare com a branch/PR e o CI do GitHub.
> Não trate roadmap antigo, memória da conversa ou documentos arquivados como estado atual.

Atualizado em: 2026-10-06 (item 5 em execução)

## Estado agora

- **Base estável (main):** V47
- **Trabalho ativo:** Estabilização e limpeza pós-V47
- **Branch/PR ativa:** nenhuma — PR #6, #7, #8, #9, #11, #12 e #13 encerradas por merge
- **Head da main:** 529b3b0274d3ac76d83789f4a09e9847ed496551
- **Status da PR #6:** merged
- **Status da PR #9:** merged — item 1 da revisão geral
- **Status da PR #11:** merged — item 3 da revisão geral
- **Status da PR #12:** merged — item 4 da revisão geral
- **Validação da PR #12:** 283 passed, 6 skipped
- **Status da PR #13:** merged — item 5, primeira extração segura do Harness
- **Validação da PR #13:** 283 passed, 6 skipped; focused visual Linux/Windows passaram
- **Status da PR #14:** merged — item 5, segunda extração segura do Harness
- **Validação da PR #14:** 283 passed, 6 skipped; focused visual Linux/Windows passaram
- **Status da PR #15:** merged — item 5, terceira extração segura do Harness
- **Validação da PR #15:** 283 passed, 6 skipped; focused Linux/Windows passaram
- **Focused visual CI:** Linux passou; Windows passou
- **Auditoria final V47:** concluída antes do merge; nenhum bloqueador funcional ou review pendente identificado.

A V47 de geometria/coordenadas foi incorporada à main pelo merge commit c0994db89aff396e0dfe43900841e0a766150b73. A main passa a ser a base estável da V47.

## Tarefa atual

**Executar estabilização e limpeza pós-V47:**

1. alinhar documentação e versão com a main V47
2. confirmar a suíte completa na main pós-merge
3. separar documentação histórica da documentação normativa
4. corrigir inconsistências encontradas sem iniciar uma nova capacidade grande

### Revisão geral em execução

- [x] item 1 — adicionar `runtime/` ao `.gitignore`
- [x] item 2 — separar decisão de permissão do canal de confirmação
- [x] item 3 — decidir por estrutura entre remover ou ligar de verdade
- [x] item 4 — remover ou mover somente código confirmado como morto
- [ ] item 5 — extrair arquivos gigantes em PRs pequenos

Situação desta rodada: versão/config/facade alinhados; a árvore atual contém apenas documentação normativa/operacional no pacote principal; o workflow agora também é acionado por push da main; o trace persistente por tarefa foi implementado e incorporado à main; no item 3, os caminhos sem efeito operacional foram removidos e o PlanBuilder foi preservado por uso real no Harness; no item 4, código sem consumidor foi removido, o wake-word foi movido para `experimental/`, e o verificador manual V46 obsoleto foi removido. `CapabilityResolver`/`IntentResolver`/`TaskSpec` e o caminho de áudio experimental permaneceram por terem chamadas reais, ainda que protegidas por flag. No item 5, a PR #13 extraiu a redação/serialização dos logs para `core/harness_logging.py`, preservando a API e os paths de sessão no Harness; a PR #14 extraiu as três heurísticas determinísticas para `core/harness_heuristics.py`, preservando os métodos estáticos no `AurenHarness` por wrappers compatíveis; a PR #15 extraiu a validação determinística de abas múltiplas para `core/harness_multitab.py`, preservando os métodos públicos do `AurenHarness` por wrappers compatíveis; o item 5 continua em execução para as próximas extrações.

## O que a PR #6 entrega

- conversão centralizada de coordenadas de imagem para coordenadas físicas/globais do Windows
- vínculo da geometria ao snapshot visual observado
- validação de resize/compressão, escala, aspect ratio, origem negativa e limites
- bloqueio de snapshot inexistente, antigo ou inseguro
- exigência de contexto DPI verificável para transformação visual
- invalidação do snapshot depois de ação visual bem-sucedida
- exigência estrutural de nova observação antes de concluir após mudança visual
- cobertura integrada captura -> geometria -> Dispatcher -> conversão -> execução
- correções de regressões da suíte e do CI

## Capacidades já concluídas ou presentes

- contratos, Router, Dispatcher, PermissionManager e ToolResult
- memória persistente em SQLite
- browser com abas/sessão persistente
- automação Windows
- busca e inteligência inicial de arquivos
- visão de tela
- clique visual
- arraste visual
- verificação de estado em tarefas visuais compostas
- voz local-first

## Próxima fase — ainda não iniciada

**Estabilização e limpeza pós-V47**

Objetivo: alinhar versão, documentação, testes, observabilidade e estado do projeto depois do merge da V47.

Critérios de saída:

- [x] README.md representa a versão real
- [x] versão/config/facade estão sincronizados
- [x] estado oficial atualizado
- [x] documentação antiga claramente separada de documentação normativa
- [x] suíte completa validada na main
- [x] trace persistente por tarefa implementado e validado na PR #8
- [x] validação visual Windows do merge mais recente concluída
- [ ] nenhuma regressão conhecida pendente

## Depois da estabilização

Próxima grande capacidade planejada:

**Browser Intelligence**

Objetivo: permitir que Auren entenda o contexto do navegador (abas, página ativa, conteúdo/estrutura relevante), aja usando as ferramentas existentes e verifique o resultado.

Esta fase só começa quando a estabilização pós-V47 estiver encerrada.

## Backlog futuro

Ideias futuras não fazem parte da tarefa atual:

- memória contextual/semântica mais avançada
- inteligência geral do Windows
- multi-device
- terminal no celular
- ESP32/Arduino
- integração com Minecraft
- wake word e experiências avançadas de voz
- interface visual estilo Jarvis

A presença de um item neste backlog **não autoriza iniciar sua implementação** enquanto a tarefa atual não estiver concluída.

## Regras de continuidade

### Uma tarefa ativa

O projeto deve ter uma única **Tarefa atual**. Todo o resto é concluído, próxima fase ou backlog.

### Estado verificável

Sempre que este arquivo for consultado, comparar:

- versão declarada em config.py/auren.py
- branch e PR ativas
- head commit
- resultado do CI
- estado real da main

Se houver divergência, corrigir o estado antes de iniciar trabalho novo.

### Toda mudança relevante atualiza o estado

Quando uma PR mudar comportamento, arquitetura, capacidade, versão ou próximo passo, o estado oficial deve ser atualizado na mesma transição.

### Sem expansão silenciosa de escopo

Uma ideia nova pode ir para o backlog. Ela só vira tarefa atual quando a tarefa anterior estiver encerrada ou quando for comprovado que ela é um bloqueador real.

### Histórico não é estado

Commits, PRs, relatórios de auditoria e versões antigas explicam o passado. Este arquivo descreve **onde o projeto está agora e qual é o próximo passo**.

## Fonte de continuidade

AUREN_STATE.md -> branch/PR -> CI -> tarefa atual -> implementação -> testes -> atualização deste arquivo