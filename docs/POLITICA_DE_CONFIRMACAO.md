# Política de confirmação do Auren

Atualizada em: 2026-10-07

## Objetivo

A regra da Tarefa 4 é simples:

> **Reversível age. Irreversível confirma. Proibido bloqueia. Leitura observa.**

A confirmação humana não deve ser usada como substituto de uma política de risco. A classificação é feita pelo Auren fora do modelo, no PermissionManager, e uma ação só executa depois de atravessar o fluxo normal:

Router → Dispatcher → Contrato → Permissão → Ferramenta → ToolResult

O Mark-LV foi usado somente como referência de problema, comportamento e casos-limite. Nenhum código do Mark-LV foi copiado.

## O que conta como cada classe

| Classe | Regra |
|---|---|
| **Leitura** | Não altera estado externo nem persistente. Pode executar automaticamente. |
| **Reversível** | A alteração tem uma forma confiável de voltar ao estado anterior, seja por undo do Auren ou por reversão local claramente definida. |
| **Irreversível** | Pode apagar, fechar, enviar, submeter, perder trabalho ou alterar estado sem uma restauração confiável. Exige confirmação humana antes da execução. |
| **Proibido** | A capacidade não deve ser executada pelo runtime. O nível correspondente é BLOCKED. Capacidades desconhecidas também são bloqueadas por padrão. |

## Matriz completa das capabilities do PermissionManager

A matriz abaixo descreve todas as 28 capabilities presentes na linha V49, incluindo as que possuem ações internas com classificação mais restritiva.

| Capability | Classificação | Nível atual | Critério / ressalva |
|---|---|---:|---|
| memory.read | Leitura | AUTO | Só consulta memória persistente. |
| memory.write | **Irreversível** | CONFIRM | Salvar pode sobrescrever valor/categoria existentes; esquecer apaga sem guardar o estado anterior exato. Não há undo confiável para a memória hoje. |
| application.open | Reversível | AUTO | Abrir um programa, por si só, não é uma alteração persistente; programas administrativos/riscos conhecidos são elevados individualmente. |
| file.search | Leitura | AUTO | Pesquisa sem mutação. |
| file.inspect | Leitura | AUTO | Inspeção e evidências locais sem escrita. Caminhos fora da política podem ser CONFIRM/BLOCKED. |
| file.read | Leitura | AUTO | Leitura controlada. Caminhos fora da política podem ser CONFIRM/BLOCKED. |
| file.manage | Reversível | AUTO | Mover, copiar, renomear e criar pasta registram undo; hashes e verificações impedem restaurar conteúdo alterado. |
| file.trash | Irreversível | CONFIRM | Usa a Lixeira do Windows, mas a restauração não é controlada pelo undo do Auren nem considerada confiável o suficiente para autoexecução. |
| windows.process.read | Leitura | AUTO | Só observa processos. |
| windows.process.control | Irreversível | CONFIRM | Encerrar processo pode perder trabalho não salvo e não tem restauração determinística. |
| windows.window.read | Leitura | AUTO | Só observa janelas e geometria. |
| windows.window.control | Reversível | AUTO | Foco, minimizar, maximizar, mover, redimensionar e restaurar são allowlisted; fechar janela continua CONFIRM. |
| windows.status.read | Leitura | AUTO | Só consulta estado do Windows. |
| windows.screen.read | Leitura | AUTO | Captura/observação sem mutação. |
| windows.clipboard.read | Leitura | AUTO | Só leitura do clipboard. |
| windows.clipboard.write | **Irreversível** | AUTO | Hoje sobrescreve o clipboard sem capturar/restaurar o valor anterior. **Mudança proposta: AUTO → CONFIRM.** |
| windows.input | Irreversível (mista) | AUTO | Movimento do mouse e teclas seguras podem ser automáticos; clique, arraste e teclas/atalhos de risco exigem CONFIRM. |
| windows.audio.read | Leitura | AUTO | Só consulta volume/mudo. |
| windows.audio.control | Reversível (mista) | AUTO | Volume e mudo capturam o estado anterior e têm undo quando a leitura anterior foi confirmada; comandos de mídia são ações momentâneas e não são registrados como undo. |
| undo.control | Reversível | AUTO | Executa somente a reversão já registrada pela pilha de undo. |
| windows.ui.read | Leitura | AUTO | UI Automation em modo de inspeção. |
| windows.ui.control | Irreversível (mista) | AUTO | Preenchimento explicitamente seguro pode ser AUTO; clique, toggle e seleção permanecem CONFIRM. |
| browser.navigation | Reversível (mista) | AUTO | Navegação comum, voltar e avançar são automáticos; recarga e destinos potencialmente persistentes são elevados para CONFIRM. |
| browser.read | Leitura | AUTO | Só observa a página/contexto. |
| browser.input | Irreversível (mista) | CONFIRM | A capacidade é conservadora; somente subações estruturalmente provadas como seguras podem receber AUTO. |
| browser.tabs.read | Leitura | AUTO | Só observa as abas. |
| browser.tabs.control | Reversível (mista) | AUTO | Abrir/trocar abas é automático; fechar aba e URLs potencialmente persistentes exigem CONFIRM. |
| browser.scroll | Reversível | AUTO | Só altera a posição de visualização e possui verificação determinística. |

## Reclassificações propostas

Nenhuma reclassificação foi aplicada nesta etapa sem aprovação explícita.

### 1. windows.clipboard.write: AUTO → CONFIRM

Motivo: a implementação atual substitui o conteúdo anterior do clipboard e não registra uma entrada de undo. Portanto, o Auren não consegue garantir que conseguirá restaurar exatamente o estado anterior.

Esse caso é o exemplo clássico da política: **parece uma alteração simples, mas não é reversível de forma confiável**.

### 2. memory.write: nenhuma promoção para AUTO

A ideia inicial de tratar memória como reversível foi rejeitada na auditoria. esquecer_memoria_persistente não é um undo: depois de uma atualização, ele não sabe qual era o valor/categoria/timestamp anterior.

Por isso, **memory.write continua CONFIRM** até existir restauração exata do estado anterior.

## Capacidades atualmente BLOCKED

Nenhuma das 28 capabilities atuais é totalmente BLOCKED.

Isso não significa que o runtime aceite qualquer capability nova. O PermissionManager resolve ausência de política como BLOCKED, e a suíte deve falhar quando uma capability nova aparecer no registry sem um nível explícito.

## Confirmação humana

A confirmação tem estas regras:

1. O modelo não fornece um parâmetro confirmed=yes ou equivalente.
2. O token é mantido pelo canal de interface e nunca faz parte dos argumentos da tool/modelo.
3. Existe no máximo uma confirmação pendente por canal.
4. A janela padrão é **90 segundos**.
5. Expirou = **não**.
6. Uma resposta atrasada ou token inválido é ignorado e nunca autoriza a ação.
7. Texto e voz usam o mesmo contrato ConfirmationChannel.
8. Uma ação nunca é executada automaticamente só porque houve timeout.

## Estado da política

A infraestrutura de timeout, expiração e token já está implementada nesta transição.

A única reclassificação material proposta e ainda pendente de aprovação é:

windows.clipboard.write: AUTO → CONFIRM

Enquanto essa aprovação não ocorrer, a política de risco permanece sem alteração no PermissionManager.
