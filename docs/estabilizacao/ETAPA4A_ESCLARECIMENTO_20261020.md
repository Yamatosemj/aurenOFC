# Etapa 4A — Tarefa aguardando esclarecimento

Candidata local sobre #177 (`e8ecc42`), restrita ao defeito B. Sem publicação,
desktop real ou mudança de arquitetura/contratos de ferramentas.

## Causa e comportamento

O guard de intenção e um ramo de fechamento registravam `needs_clarification`,
mas chamavam `TaskManager.complete(pergunta)`. Perguntas textuais também podiam
chegar ao finalizador de sucesso. O próximo envio sempre criava outra tarefa;
trocar somente COMPLETED por WAITING bloquearia essa criação, sem continuidade.

Esclarecimento dirigido agora usa o estado existente **WAITING**, sem resultado
final/finished_at. Um vínculo privado, em memória no mesmo Harness/chat, mantém
task_id, restrições e trace; a resposta aceita retoma a mesma tarefa RUNNING,
preservando objetivo original, plano, passos e histórico. A pergunta entra no
contexto da continuação; não substitui o pedido original nem autoriza ferramentas.
Não há enum, schema, tabela ou camada de memória nova.

As ações continuam pelo Router/Dispatcher/contratos/PermissionManager normais.
Limites de permissão são restaurados como restrições, sem aprovações; o escopo
anterior é combinado com o atual, nunca ampliado. Orçamento persistente de
modelo não é renovado. Flags de verificação visual/browser pendentes são
preservadas, mas coordenadas/snapshots de visão não são reutilizados.

Efeitos concluídos não são repetidos na continuação: comparação conservadora
de ferramenta/argumentos canonizados e redigidos interrompe a repetição. Leitura
pode ser repetida quando necessária como nova prova após outro efeito. Uma
falha anterior não é apagada por esclarecimento; recuperação C não foi alterada.

Negativa/cancelamento encerra a tarefa original como CANCELLED. Botão de cancelar
enquanto aguarda, shutdown e fechamento/troca de sessão limpam a pergunta. Um
pedido novo explicitamente reconhecido cancela o anterior e recebe identidade
própria. Respostas vazias/inconclusivas e “sim” para pergunta informativa como
“qual volume?” mantêm a espera; não disparam modelo/ferramenta. Perguntas sociais
e convites de conversa não criam pendência; preservado o guard de confirmação
repetida. Prompts explícitos do revisor não dependem de pontuação final.

Trace é mantido entre os turnos e finalizado quando a tarefa termina, sem criar
outra linha com o mesmo task_id. Erro de trace no cancelamento não impede limpeza.

## Validação e limites

`tests/test_clarification_task_state.py` cobre memória/SQLite descartáveis,
estados internos, identidade, continuidade, progresso parcial, duplicação,
cancelamento, falha, respostas inconclusivas, nova sessão/pedido, escopo expirado,
orçamento e negativa de permissão. Uma expectativa antiga que afirmava COMPLETED
para esclarecimento foi corrigida para WAITING em `test_intent_verification.py`.

```powershell
python -m pytest -q tests/test_clarification_task_state.py
```

Relatório externo 4A registra SHA local, comparação vermelha/verde, suíte offline
selecionada e integração pela fábrica com Router/Dispatcher/PM reais, provider e
executores falsos. Não confundir com modelo, volume, desktop ou UI físicos.

Vínculo/pergunta/escope de esclarecimento **não são restaurados após reinício**.
O armazenamento existente pode preservar/interromper a tarefa, mas isso não
certifica retomada do esclarecimento; avaliar na etapa 5. Classificação local de
texto/novo pedido é conservadora e limitada; respostas curtas não reconhecidas
passam pelo ciclo e revisor usuais, não por autorização implícita. O guard contra
repetição pode rejeitar efeitos iguais legitimamente pedidos de novo; não há
replay automático ou rollback de efeitos já realizados.

D, A, C, 28 executores reais, testes visuais/foco/DPI e YouTube público permanecem
no backlog. Não há necessidade técnica de Live para o defeito de estado: custo
desta etapa zero; teto acumulado de US$ 1,00 preservado. CI/publicação dependem de
próxima autorização, sem avanço automático.
