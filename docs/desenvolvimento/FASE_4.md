# Fase 4 — acompanhamento na interface existente

Base: Fase 3, `2313f1d`, [CI 39129372163](https://github.com/Yamatosemj/aurenOFC/actions/runs/39129372163): 1.055 aprovados Windows; 1.011 aprovados/44 ignorados Linux. Branch própria `desenvolvimento/fase-4-interface-tarefas`, sem merge.

## Auditoria e integração

Foram lidos o worker, ciclo de geração/confirmação/desligamento, servidor HTTP local, página Chrome, GUI Tk e testes existentes. O worker já serializa mensagens e encaminha confirmações ao Harness; as telas não precisam de outro executor. A API de histórico/rotinas das fases anteriores foi ligada a esse mesmo worker.

O worker padrão usa `data/tasks/auren_tasks.sqlite3`, separado da memória de conversas. Só abre o Harness no primeiro pedido de mensagem ou de carregar tarefas; abrir a tela não dispara ferramentas, modelo ou autorização de rotinas. Factory de teste continua injetável; `task_db_path=False` desliga essa persistência explicitamente no worker. CLI/voz mantêm seu padrão anterior, com `task_db_path` disponível na fábrica para integração explícita. Nenhum banco pessoal foi aberto ou migrado nesta implementação: os testes usam somente caminhos temporários.

O fechamento passa pelo `Harness.shutdown`, que libera a conexão/trava do TaskManager. Desligar/fechar preserva tarefa já pausada/interrompida, sem transformá-la em pedido de cancelamento. Tarefa em execução mantém cancelamento cooperativo. Cancelar pelo botão é uma ação explícita e persiste o cancelamento, inclusive para tarefa pausada.

## Controles visíveis

No Chrome, o painel **Tarefas e rotinas** oferece carregar histórico, selecionar conversa salva, acompanhar estado, passos realmente executados, plano estimado, uso de chamadas e histórico recente. Botões enviam pausa, cancelamento e retomada; não alteram o estado apenas na página. Retomada insegura é desabilitada e explicada. Não há porcentagem inventada a partir da quantidade de ferramentas: passos executados não equivalem a objetivo concluído.

A seleção de conversa reutiliza somente o identificador lógico já conhecido pelo banco. Cria um caminho de log novo, nunca recupera um caminho arbitrário salvo, não retoma objetivo automaticamente e não desanexa tarefa em execução. O histórico é consultado por chat, com até 50 objetivos por tela e até 20 passos recentes por objetivo. Objetivos anteriores permanecem no armazenamento, embora esta primeira tela não tenha paginação de arquivos muito grandes.

O formulário de rotina oferece lembrete local livre ou consulta de volume/status do sistema. Os dois últimos tipos possuem escopo fixo de leitura e até uma chamada de IA por ocorrência; custo possível é mostrado antes do cadastro. O usuário define primeiro horário, vencimento, intervalo e quantidade. **Salvar rascunho não autoriza**: a rotina aparece com condições e um botão separado de autorizar agendamento. Há revogação explícita. A lista exata de outras ferramentas/argumentos executáveis continua disponível somente na API interna da Fase 3; a tela não tem editor genérico de ferramentas.

O worker verifica a agenda enquanto sua sessão está habilitada e o chat proprietário está selecionado, sem outra tarefa pendente. Não executa com app fechado ou sessão Desligada, não ativa rascunhos ao abrir a tela e não despeja ocorrências atrasadas. Standby visual não é pausa de tarefa ou desligamento do worker; rotinas autorizadas podem ser acompanhadas enquanto a sessão continua habilitada. Sugestões são avisos locais, sem mensagens externas. Se uma ação exigir confirmação enquanto a interface não puder aceitá-la, a recusa permanece válida.

Tk recebe tabela de objetivos, seleção de conversa e os mesmos controles de pausa/cancelamento/retomada, com consulta periódica do estado real. Cadastro/autorização de rotinas ficam no Chrome nesta fase. Não há reescrita do orbe, implementação Electron ou integração de PR excluída.

## Sessão, concorrência e segurança

Comandos HTTP continuam exigindo 127.0.0.1, token local, origem válida, JSON e schema limitado. Controles incluem a geração da sessão. Cards capturam a geração que os produziu; controle/autorizações antigos são recusados depois de Desligar/reativar. Autorizar uma rotina é conferido no worker sob a mesma trava usada para invalidar a geração. O conteúdo de objetivo/histórico é exibido com `textContent`, não como HTML.

Foi reproduzida uma corrida no intervalo entre a conferência de geração e a criação do objetivo: Desligar não encontrava ainda uma tarefa para cancelar, e a chamada ao modelo podia começar depois. A reprodução falhou antes do ajuste. Agora uma guarda de sessão por ContextVar acompanha a execução, é conferida antes de chamar o modelo e pelo Dispatcher, inclusive após confirmação. Essa guarda não substitui o escopo de rotina, não concede autorização e não impede publicar checkpoint seguro da tarefa normal. ContextVars são restauradas ao sair. Cancelamento permanece cooperativo; chamada/efeito já iniciado pode terminar e não é revertido.

## Testes e limites

Oito casos novos exercitam armazenamento/worker/HTTP reais: carregar e selecionar objetivo após reabrir banco, continuar o mesmo ID sem repetir passo, fechar e liberar banco preservando pausa, cancelar pausa, rejeitar geração antiga, desligar antes da criação do objetivo, consultar progresso WAITING e depois PAUSED gravado, cadastro separado de autorização/revogação e schemas/token/geração no HTTP. Os modelos e efeitos são fictícios; confirmações continuam pelo canal existente. Seleção focada: 43 aprovados, zero falhas, sobreposta à suíte completa.

Não foi validada nesta fase a aparência física das telas, acessibilidade por leitor de tela, DPI/fontes, browser/GUI reais com API, dispositivo, custo/latência ou muitas conversas. A Fase 5 deve exercitar integração e interface em ambiente isolado quando possível; chamadas pagas continuam sem orçamento definido. Não foi feita migração/importação de bancos reais, instalação do runner, alteração de workflow, hardware ou merge na main.

Resultados, reproduções e hashes: `fase4/RESULTADOS_FASE_4.json`. O avanço exige suíte completa e CI Windows/Linux no SHA final, registrado na PR.
