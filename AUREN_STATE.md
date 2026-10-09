# Auren — Estado oficial do projeto

> Fonte de verdade operacional do Auren.
> Antes de iniciar uma nova tarefa, compare este arquivo com a branch/PR, o head da main e o CI do GitHub.
> Histórico, memórias da conversa e documentos arquivados não substituem este estado.

Atualizado em: 2026-10-09

## Estado atual

- **Versão estável:** V47
- **Modelo padrão:** `gpt-5.6-luna`
- **Branch/PR ativa:** nenhuma nesta rodada; PRs de funcionalidades antigas continuam separadas e nao foram integradas automaticamente
- **Head da main:** consultar GitHub antes de cada tarefa; ultimo merge de codigo confirmado: PR #106 (`d7b55026404a7c0331b48a36ee8d3346b586a95a`)
- **CI:** PRs #105 e #106 com suite completa Linux e testes focados Linux/Windows verdes; validar separadamente os workflows de push e a bateria live no PC
- **Fase atual:** Browser Intelligence

### Seguranca A01 — incorporada na main (PR #99)

- A falha anterior fazia leituras externas ja marcadas como nao confiaveis deixarem de ativar a guarda de confirmacao. Corrigida na main pelo merge da PR #99.
- `tools/dispatcher.py` registra a fonte em toda leitura bem-sucedida de `ler_arquivo`, `ler_pagina` e `obter_contexto_navegador`, mesmo com a flag previamente ativa.
- Regressoes: tres casos reproduziram falha antes da correcao; depois, suite completa do CI Linux retornou 445 passed e 6 skipped.
- Esta correcao nao implementa A02/A03. O A04 tambem foi incorporado na main pela PR #104.

### Seguranca A04 — bloqueio absoluto integrado na main (PR #104)

- `core/permission_manager.py` tinha precedencia incorreta: apos conteudo externo, uma capacidade `BLOCKED` contada podia virar `CONFIRM`.
- `PermissionManager` agora aplica `BLOCKED` antes da guarda de origem externa; AUTO ainda sobe para CONFIRM apos leitura nao confiavel.
- Testes para ambos os cenarios passaram na PR #104, assim como o teste A01 ajustado sem contornar a protecao de AppData no Windows.
- A02 foi corrigido na branch da PR #81 por merge da PR #100 (`12b72d1`), com aprovacao obrigatoria antes do import. As PRs #81/#84 ainda nao foram incorporadas a `main` e seguem exigindo revisao de conflitos e integracao. A03 (pesquisa web) tambem permanece fora da `main`.

### Confirmacao por voz — PR #105 incorporada na main

- Em V47, a confirmacao podia consumir audio antigo da fila e nao verificava estritamente o envelope de `CapturedAudio`.
- Agora descarta a fila antes do prompt, aceita somente um envelope `("audio", CapturedAudio)` novo e exige afirmacao explicita. Negacao e resposta ambigua nao autorizam.
- Comandos de saida textuais/falados aceitam pontuacao mantendo correspondencia exata.
- CI da PR #105: suite completa Linux 494 passed/15 skipped, focused Linux 119 passed/6 skipped e focused Windows 125 passed.
- O codigo especifico desta correcao foi portado da PR #92 para a V47. Ao integrar a cadeia V48 (#85, #90, #92, #95), reconciliar as alteracoes duplicadas; nao executar merge cego nem tratar como validacao fisica de microfone.

### Preservacao de origem visual — PR #106 incorporada na main

- O Dispatcher reconstruia `ToolResult` ao anexar `vision_coordinate_transform`, mas perdia `conteudo_nao_confiavel`; a reconstrucao agora preserva a marca de proveniencia.
- Regressao testada para sucesso e falha, incluindo `for_model()`, `as_dict()`, `error_code` e metadados de geometria.
- CI da PR #106: suite completa Linux 496 passed/15 skipped, focused Linux 128 passed/6 skipped e focused Windows 134 passed.
- Nao substitui exercicios reais de visao+acao+verificacao no Windows.

### CI de revisao de PRs (PR #104)

- Workflows de pytest completo e testes focados agora usam `pull_request` para a `main` em runners hospedados do GitHub, alem do push normal.
- Regressao de prompt injection incluida na bateria focada Linux/Windows.
- Na PR #104, o workflow completo Linux e os dois jobs focados Linux/Windows concluiram com sucesso.
- Ainda falta validar a bateria funcional live de Auren+modelo+navegador no PC, independente da suite pytest.

### O que já está concluído nesta fase

- [x] contexto unificado do navegador via `obter_contexto_navegador`
- [x] contexto disponível no registry, contratos, facade e Dispatcher
- [x] Router inclui contexto junto do subconjunto de ferramentas do browser
- [x] conteúdo da página marcado como não confiável
- [x] tarefas browser compostas com ações relevantes exigem nova verificação antes da conclusão
- [x] verificação usa `obter_contexto_navegador` pelo fluxo normal do modelo/Dispatcher
- [x] ações browser simples preservam o comportamento anterior e não ganham uma rodada extra desnecessária
- [x] navegação e troca de aba têm verificação determinística de URL/aba ativa
- [x] preenchimento de campos não sensíveis tem verificação determinística do valor observado
- [x] rolagem expõe métricas estruturadas e possui verificação determinística da posição observada
- [x] runner live separado possui casos explícitos de verificação pós-ação para navegação e rolagem

### Próximo passo da fase

**Refinar a verificação por tipo de ação**, mantendo o princípio de não criar novas integrações:

- navegação: confirmar título/URL efetivos — **parcialmente concluído**; URL já é comparada de forma determinística
- abas: confirmar quantidade, aba ativa e destino — **parcialmente concluído**; aba ativa já é comparada de forma determinística
- interação com elemento: confirmar o estado relevante da página ou controle — **parcialmente concluído**; preenchimento não sensível já é comparado pelo valor observado
- rolagem: posição de rolagem já é verificada deterministicamente; confirmar automaticamente o conteúdo esperado continua como etapa posterior
- qualquer verificação continua tratando conteúdo da página como dado não confiável, nunca como instrução

## Segurança e base estrutural concluídas

- [x] allowlist de leitura/inspeção de arquivos
- [x] defesa contra prompt injection de conteúdo não confiável
- [x] política de permissões endurecida
- [x] exceções genéricas reduzidas em caminhos críticos
- [x] dependências principais fixadas
- [x] modelo configurável por ambiente com padrão `gpt-5.6-luna`
- [x] Windows dividido por domínio
- [x] Browser dividido em leitura, elementos e navegação
- [x] Harness dividido em runtime, guards, ciclo e demais mecanismos
- [x] runner live separado da suíte pytest
- [x] trace persistente por tarefa
- [x] validação visual Windows com geometria/coordenadas protegidas

## PRs mais recentes

- **#48** — extração de Windows UI Automation — merged
- **#49** — extração de status do Windows — merged
- **#50** — extração de captura de tela — merged
- **#51** — extração de leitura do Browser — merged
- **#52** — extração de interação com elementos do Browser — merged
- **#53** — extração de navegação do Browser — merged
- **#55** — extração do runtime de sessão/logging do Harness — merged
- **#56** — extração do ciclo de execução do Harness — merged
- **#57** — separação do runner live de regressão — merged
- **#58** — Browser Context Intelligence inicial — merged
- **#60** — contexto do Browser incluído no roteamento especializado — merged
- **#61** — verificação após ações relevantes do Browser — merged
- **#64** — verificação determinística de navegação e troca de aba — merged
- **#66** — verificação determinística de preenchimento de elemento — merged
- **#69** — verificação determinística de rolagem e persistência da evidência entre rodadas — merged
- **#72** — cobertura do Browser Intelligence no runner live — merged

## Contratos atuais importantes

- Conteúdo vindo de páginas web é **dado não confiável**
- Conteúdo não confiável nunca autoriza uma ação por si só
- Ações continuam passando pelo Router, Dispatcher e PermissionManager normais
- Não existe caminho paralelo de execução para Browser Intelligence
- A tarefa não deve declarar sucesso quando uma verificação obrigatória ainda estiver pendente
- Mudanças de escopo devem virar backlog, não execução silenciosa

## Próximas etapas

A tarefa ativa permanece **Browser Intelligence** até que a verificação por tipo de ação esteja suficientemente robusta e coberta por testes.

Próxima etapa: executar o runner live em Windows e registrar o resultado real das tarefas compostas. O CI atual valida o código do runner, mas não executa a bateria L4/L5 com navegador e modelo reais.

Depois disso, revisar novamente a estabilização e só então abrir novas frentes.

## Backlog

Ideias futuras que não fazem parte da tarefa atual:

- memória contextual/semântica mais avançada
- inteligência geral do Windows
- multi-device
- terminal no celular
- ESP32/Arduino
- Minecraft
- wake word
- interface visual avançada

## Regra de continuidade

Toda mudança relevante de arquitetura, comportamento, capacidade, versão ou próximo passo deve atualizar este arquivo na mesma transição.

Fluxo oficial:

`AUREN_STATE.md → branch/PR → CI → implementação → testes → atualização do estado`

## Automação remota de testes — 2026-10-09

- Workflow manual pytest nos runners do GitHub disponível, com logs e JUnit.
- Repositório confirmado privado nesta inspeção.
- Workflow manual de conexão Windows preparado, sem checkout/imports do Auren.
- Runner Windows local foi registrado e conexao validada na execucao #37884137457; atualizacao remota da main validada na #37890091132.
- Workflow live foi habilitado com supervisao e limites; tentativas iniciais de ALL revelaram erros de descoberta/aliases posteriormente corrigidos. Nao ha evidencia aqui de validacao funcional ALL completa.
- Estado e próximos passos: [Testes pelo GitHub](docs/TESTES_GITHUB.md).
