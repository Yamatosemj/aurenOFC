# Estabilização funcional

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
Resultados finais e situação da próxima etapa serão registrados abaixo.
