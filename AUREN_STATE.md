# Auren — Estado oficial do projeto

> **Este arquivo é a fonte de verdade operacional do Auren.**
> Antes de iniciar uma nova tarefa, consulte este arquivo e compare com a branch/PR e o CI do GitHub.
> Não trate roadmap antigo, memória da conversa ou documentos arquivados como estado atual.

Atualizado em: 2026-10-06 (auditoria final V47)

## Estado agora

- **Base estável (main):** versão declarada V46
- **Trabalho ativo:** PR #6 — feat: robustecer coordenadas da visão no Windows
- **Branch ativa:** feat/robust-vision-coordinates-v47
- **Head da PR:** 19a89a1759a04e0f44ce825ecc2b92ea8280e988
- **Status da PR:** aberta e mergeável
- **Validação da PR:** 280 passed, 6 skipped
- **Focused visual CI:** Linux passou; Windows passou
- **Auditoria final V47:** concluída; nenhum bloqueador funcional ou review pendente identificado. PR #6 está pronta para merge, mas permanece aberta conforme o controle de escopo.

A main já contém as melhorias anteriores de visão/ação e tarefas visuais compostas. A V47 de geometria/coordenadas ainda não deve ser tratada como estável até a PR #6 ser incorporada.

## Tarefa atual

**Finalizar a transição para V47:**

1. manter a PR #6 como único trabalho ativo
2. não iniciar uma nova feature grande antes de a PR #6 entrar na main
3. após o merge, atualizar este arquivo para registrar V47 como estável
4. só então iniciar a próxima fase

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

Objetivo: alinhar versão, documentação, testes e estado do projeto depois do merge da V47.

Critérios de saída:

- [ ] README.md representa a versão real
- [ ] versão/config/facade estão sincronizados
- [ ] estado oficial atualizado
- [ ] documentação antiga claramente separada de documentação normativa
- [ ] suíte completa validada na main
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