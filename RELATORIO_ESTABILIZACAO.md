# Estabilização funcional

> Continuação: a entrega persistente de avisos foi implementada depois deste
> diagnóstico, em branch própria baseada na #162. Consulte os
> [resultados atuais, falhas Live e limites](docs/estabilizacao/AVISOS_DURAVEIS.md).
> O relato abaixo preserva a interrupção e as evidências da etapa anterior.

Base: candidata da PR #161, `af84aec70b1ada2998283388cd73b55bd817c504`.
Branch isolada: `estabilizacao/continuidade-lembretes-20261018`.
Main e Electron (#141/#142) permanecem fora das alterações.

## Etapa 1 — Continuidade

Causa: qualquer resposta terminada em interrogação, sem efeitos anteriores,
era guardada como esclarecimento. Uma conversa sem ferramentas também atendia
essa condição. Além disso, o filtro de novos comandos não reconhecia verbos
como criar, lembrar, cancelar e adiar.

Correção: distinguir convites sociais de perguntas dirigidas antes de guardar
ou consumir a pendência. Comandos novos seguem como objetivos próprios.
Perguntas sobre cor, arquivo, horário e confirmações continuam no fluxo anterior;
nenhuma resposta contextual substitui a autorização do PermissionManager.
O filtro continua local e linguístico: não é uma classificação semântica infalível
de toda frase possível. As formas reproduzidas estão cobertas por regressões.

Evidências: primeira tentativa de teste teve erro de coleta (nome reservado do
pytest), corrigido antes da reprodução. Em seguida, 10 falhas e 3 aprovações
reproduziram os defeitos antes da mudança de produção. Após a correção, 52 testes
focados passaram, incluindo as regressões anteriores de confirmação e fechamento.
Dois casos adicionais verificam pendência social antiga e consumo único.
Resultado focado final: **54 passaram, 0 falharam** (15 novos casos).
Suíte completa local Windows/Python 3.13: **1.088 passaram, 8 ignorados,
0 falhas**, em 75,96 segundos, com avisos de exceções de threads tratados como
erros. Os oito ignorados são os casos existentes de links simbólicos sem o
privilégio necessário. Execução em cópia somente de fontes, perfil fictício,
sem credenciais, protegida pelo watchdog existente. Resultado em
`C:\Windows\Temp\auren-integracao-20261018-4c38\stabilization-full\result.xml`.
O código testado corresponde ao commit `4da6d74`; depois dele, somente este
relatório foi ampliado. Não foi executado Live com modelo ou efeitos reais.

## Etapa 2 — Diagnóstico e interrupção da expansão

Referências comparadas: #161 no SHA acima e #137 no SHA
`09a67659a82121449e3340538200780688c0b6de`. A #137 foi apenas lida;
não foi mesclada nem copiada para a candidata.

| Ponto | #161 | #137 |
| --- | --- | --- |
| Persistência | TaskManager e tabelas de rotinas no mesmo banco | ReminderStore em outro banco |
| Autorização | Rascunho, autorização separada, escopo por chat | Ferramentas específicas e política própria |
| Execução | Um worker, apenas chat selecionado e sem tarefa ativa | Thread de lembretes no servidor Chrome |
| Entrega | Ocorrência consumida antes de publicar evento temporário | Aviso persistido até confirmação da interface |
| Alteração | Autorizar e revogar; sem adiamento | Adiar, cancelar e concluir |

Achado adicional concreto: `ui/backend.py` publica lembretes como `notice`, mas
a função `evento` em `ui/chrome.html` não trata `notice`. Portanto, o evento no
backend **não comprova exibição de lembrete no Chrome**. O teste integrado
anterior confirmou o evento, não esse resultado visual. Essa limitação corrige
a interpretação anterior das evidências; não é uma funcionalidade já entregue.

O estado atual também permite uma janela de perda: o scheduler persiste
`exhausted` antes de o worker publicar o aviso. Se o processo cair nesse
intervalo, não há confirmação persistida de exibição nem reentrega desse aviso.
Não se deve resolver isso repetindo execuções de rotinas com efeitos incertos.

A extensão necessária é maior que registrar três ferramentas: envolve entrega
durável, compatibilidade dos registros existentes, alterações concorrentes,
separação entre lembrete entregue e ação executada, ciclo de sessão e testes
de interface. Conforme a regra de interromper expansão significativa, esta
etapa fica **diagnosticada, sem implementação**, antes de mudar esse contrato.

Plano técnico para retomar, mantendo um único sistema:

1. Manter RoutineScheduler/TaskManager como fonte única. Reaproveitar da #137
   o interpretador de horários, os contratos úteis e o conceito de confirmação
   visual; não importar o singleton, banco ou thread independente.
2. Persistir avisos pendentes na mesma transação que consome a ocorrência.
   Reentregar avisos sem repetir a execução da rotina. Confirmar a exibição
   somente depois de renderizar; cobrir recarga, queda e reconexão.
3. Oferecer criação, consulta, alteração e cancelamento pelo Dispatcher normal,
   com permissões, identidade do chat e resolução segura de referências ambíguas.
4. Acrescentar adiamento transacional e controle de versão da ocorrência, para
   que uma confirmação atrasada não descarte o aviso reagendado.
5. Verificar no navegador o texto visível, o novo horário persistido e o
   cancelamento, com relógio e modelo simulados; preservar rotinas existentes.

Comportamento **atual da #161**, não promessa da futura implementação:

- Aplicativo ativo: consulta rotinas quando o worker fica ocioso, apenas no chat
  selecionado. Uma tarefa longa pode atrasar a consulta. O Chrome não renderiza
  o `notice` de lembrete nesse caminho.
- Standby: muda o modo visual; não desativa o worker. Permanecem as restrições
  de chat/tarefa e a limitação visual descritas acima.
- Sessão desligada: o worker invalida a sessão e descarta o scheduler; não
  consulta as rotinas até reativação e seleção do contexto apropriado.
- Processo encerrado: não há mecanismo externo de alerta. A persistência de
  rotinas não significa entrega enquanto o processo está parado. Ao reabrir,
  rotinas vencidas podem expirar; avisos já consumidos não são reentregues.

Nenhum banco pessoal foi consultado ou migrado. A compatibilidade com dados
da #137 deve ser testada com registros fictícios antes de qualquer migração.

## Etapas seguintes e limites

Etapas 3, 4 e 5 não implementadas, pois dependem da etapa interrompida.
Não houve medições novas da descoberta de aplicativos nem alteração do Router.
Os 36 segundos do log não permitem atribuir o tempo a uma causa específica.
Não houve chamadas pagas, execução de aplicativos pessoais, mudança na main,
integração de Electron ou redesign. A correção de continuidade não entrega
timers, lembretes pelo chat ou recuperação geral nova.
