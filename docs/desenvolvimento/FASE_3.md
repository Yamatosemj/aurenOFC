# Fase 3 — rotinas e proatividade controlada

Base: Fase 2, commit `a2b0961`, [CI 39128640968](https://github.com/Yamatosemj/aurenOFC/actions/runs/39128640968) aprovado com 1.044 testes Windows e 1.000 Linux/44 ignorados. Branch própria `desenvolvimento/fase-3-proatividade-controlada`; sem merge. Main consultada novamente em `70b040d6191237e2f0a291a14b8ea8fb4b78a09d`.

## Auditoria e escolha técnica

A busca em core/agent/ui e a leitura da fila `AgentTaskQueue` confirmaram que ela executa callbacks auxiliares em threads e guarda resultados em memória. Não persiste agenda, autorização ou reserva de disparo e não é a fila operacional de objetivos. Não foi reaproveitada para disparar ferramentas. O novo `RoutineScheduler` usa a mesma conexão SQLite e trava do TaskManager para **metadados de agenda**; a execução continua criando objetivos no TaskManager e passando pelo único Harness/ciclo/Dispatcher. Não há outro executor, banco paralelo ou nova ferramenta exposta ao modelo.

## Funcionamento

Uma rotina começa em rascunho. Possui chat proprietário, objetivo, horário, vencimento, intervalo, quantidade máxima de disparos e modo. `suggest` só produz uma sugestão local; não chama modelo ou ferramenta. `execute` exige lista exata de ferramentas **e argumentos** permitidos e limite de chamadas ao modelo por disparo. `authorize` é uma API interna para autorização explícita do usuário; cadastro, texto de arquivo/site, resposta do modelo e a própria rotina não a invocam. A interface de autorização pertence à Fase 4. Aprovar uma rotina não aprova confirmações do PermissionManager.

`tick` só avalia o chat informado e processa no máximo uma rotina vencida por chamada. Executar exige o mesmo TaskManager e o chat proprietário ativo no Harness. O intervalo mínimo é 60 segundos, com até 1.000 disparos por cadastro; execução tem até 20 chamadas ao modelo por disparo e até 20 chamadas distintas no escopo. Tudo permanece sujeito a tetos menores do Harness, revisão e PermissionManager. Esses são limites técnicos máximos, não autorização para gastar crédito. Nenhuma API paga foi chamada nos testes.

A reserva do disparo, seu identificador e consumo de quantidade são gravados **antes** de qualquer efeito. Falha ao gravar impede o disparo. Horários atrasados são condensados em uma ocorrência, sem despejar uma fila de execuções perdidas. Reinício não repete a mesma ocorrência. Se o processo cair depois da reserva e antes de confirmar o resultado, a rotina fica interrompida e exige investigação; não é tentada outra vez automaticamente.

O escopo é uma restrição adicional em ContextVar. O ciclo rejeita propostas fora da lista exata antes da execução e o Dispatcher confere também antes dos preflights e novamente depois da confirmação do PermissionManager, antes do handler. A conferência consulta revogação/vencimento e o identificador atual do disparo. Escopos aninhados só podem restringir mais, e são removidos em finally ao sair. Não há chave de bypass, confirmação automática, ampliação do registry ou restauração de aprovações. Um objetivo de rotina não publica checkpoint executável que possa depois ser retomado sem seu escopo.

Rotina falha/interrompida/revogada não é reativada por uma autorização genérica: o cadastro deve ser revisto. `revoke` impede novos passos; não interrompe à força operação que já entrou no handler nem desfaz efeitos. O intervalo entre a última conferência e a entrada no handler continua sendo um limite de cancelamento cooperativo; não há promessa de transação atômica entre banco e mundo externo.

## Testes e limites

Oito casos iniciais falharam antes de existir o componente. Outro teste mostrou que uma rotina podia entrar em um Harness de outro chat; o código passou a recusá-lo antes de consumir o disparo. São testados SQLite real, aprovação separada do cadastro, isolamento entre chats, sugestão sem modelo, persistência, horário atrasado, reserva única, esgotamento, revogação, expiração durante confirmação fictícia, proposta fora do escopo e reserva SQL abortada. Um teste tinha a classe de exceção SQL incorreta: `RAISE(ABORT)` produziu `IntegrityError`; a expectativa foi corrigida para essa classe, mantendo a exigência de não disparar e não consumir quantidade.

Uma rotina de leitura autorizada passa pelo Harness/Dispatcher/PermissionManager reais, executa duas consultas fictícias em horários distintos e fica esgotada. Cada objetivo tem exatamente uma chamada ao modelo, dentro do limite cadastrado. Negativa, revogação e expiração não executam o handler, mesmo com autorização positiva **simulada** do canal nos dois últimos casos. As seleções se sobrepõem e não devem ser somadas.

A agenda não inicia thread, rede, serviço do Windows ou modelo implicitamente. Nesta fase existe API interna, sem integração visual ou loop de polling no aplicativo. A Fase 4 deve ligar o acompanhamento à interface existente, mostrar escopo/prazo/limites e exigir ação explícita de autorizar. Ao abrir ou reativar uma interface, não autorizar rascunhos automaticamente. Não foram testados programas pessoais, dispositivos, browser físico, API/modelo reais, custos, execução com app fechado, alterações hostis do banco ou migração de dados reais. Rotinas não enviam mensagens externas. A ligação a ferramentas respeita os mesmos limites de segurança e verificações da Fase 2.

Resultados e falhas intermediárias: `fase3/RESULTADOS_FASE_3.json`. Só avançar depois da suíte completa e CI Windows/Linux aprovados no SHA final, registrado na PR.
