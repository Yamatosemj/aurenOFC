# Correções das falhas Live — Fase 5

## Resultado atual

As duas falhas continuam confirmadas na base e foram corrigidas na branch `desenvolvimento/fase-5-correcoes-live`, criada a partir de `a4e1f8b`. Main preservada; nenhuma PR mesclada. O código final passou na suíte completa local: **1.069 aprovados, zero falhas e oito ignorados**, em **62,64 segundos**. Os ignorados exigem links simbólicos indisponíveis neste Windows. O CI do HEAD final deve ser consultado na PR das correções.

A pendência do contrato final descrita nesta bateria foi encerrada posteriormente: três casos com API real passaram. [Validação final](VALIDACAO_FINAL.md). O histórico abaixo preserva o que motivou o ajuste final.

## F5-LIVE-002 — confirmação respeitada

Antes, uma pasta permitida podia fazer o Auren ignorar a configuração “exigir confirmação”. Agora leitura e inspeção mantêm essa exigência mesmo dentro de Documents. BLOCKED continua absoluto; caminho sensível continua bloqueado; caminho fora das raízes permitidas continua exigindo confirmação.

Primeira reprodução: dois testes falharam (ler/inspecionar com CONFIRM) e dois passaram (BLOCKED). Depois da mudança, os quatro passaram. Os testes verificam o Dispatcher, a solicitação negada e a ausência de chamada ao executor. Uma execução adicional com Dispatcher, PermissionManager e executores de arquivos reais configurados, sobre TXT fictício, também recusou leitura e inspeção quando a confirmação foi negada; não chamou API. Nenhuma confirmação positiva foi aprovada automaticamente.

## F5-LIVE-001 — conferir a resposta que será entregue

O Harness agora envia uma cópia da resposta candidata ao revisor, sem gravá-la como resultado ou publicar sucesso antes da verificação. O revisor recebe objetivo, plano e evidências, além desse texto. A resposta é dado sem autoridade: não pode mandar o revisor aprovar nem alterar permissões.

As instruções distinguem leitura bem-sucedida de autoridade para dar ordens: um TXT pode fornecer números para a soma sem autorizar ações externas. O revisor confere códigos, cálculos e alvos. A restrição de usar somente dois arquivos é conferida no histórico; reler um alvo permitido não vira uma violação por si só. Para ações com efeito, a leitura posterior continua obrigatória.

Se apenas a resposta precisa ser corrigida, a única recuperação permitida pode ajustar texto/cálculo sem obrigar uma nova ferramenta. O motivo do revisor é devolvido como dado, com tamanho limitado; permanece uma tentativa de recuperação, orçamento acumulado e revisão antes do sucesso. Dados ausentes ainda podem exigir ferramenta, passando pelas permissões normais.

A primeira rodada local ficou vermelha antes da mudança: quatro casos falharam por resposta candidata ausente e falta de limite para seu tamanho. Depois, resposta correta concluiu; soma errada e texto tentando mandar aprovar permaneceram bloqueados. Resposta longa é recusada, sem corte silencioso. Outro teste confere recuperação de soma 99 para 18 sem uma terceira ação.

## O que o novo Live mostrou e o ajuste final

Cinco novas chamadas reais, numeradas 20–24 no registro acumulado. As quatro primeiras executaram leitura, pausa, retomada, resposta e revisão: mesmo objetivo terminou corretamente com duas etapas, somente o segundo arquivo lido depois de retomar, códigos ALFA-731/BETA-982 e soma 18.

Na quinta chamada, o teste enviou a mesma evidência completa com a soma alterada para 99. O revisor identificou no texto do diagnóstico que a resposta estava errada, mas marcou todas as etapas como verified. O teste reprovou; esse resultado está preservado. A mensagem antiga do script diz “missing evidence”, porém nesta execução o estímulo era **soma errada com evidência completa**, conforme código do script e JSON. Não se tratou de aprovação de evidência ausente nessa rodada.

Para fechar essa lacuna, o contrato estruturado agora exige **answer_status** separado das etapas. Somente `verified` para a resposta **e** todas as etapas com referências válidas permitem conclusão. Estado ausente/inválido é erro; `pending` ou `failed` impede sucesso e só permite a recuperação limitada já existente. A validação das referências e a exigência de observação posterior aos efeitos continuam iguais. Não se usa busca por palavras do diagnóstico como decisão.

Reprodução local antes do ajuste final: **um falhou/11 passaram**; um resultado com todas as etapas aprovadas e resposta não aprovada era aceito. Depois do ajuste: **33 testes focados passaram**, incluindo campo ausente, resposta pending/failed, soma errada, tentativa de instrução, referências inexistentes, efeito sem leitura posterior, retomada em outro processo e resposta corrigida sem repetir ação. Fixtures existentes receberam o novo campo obrigatório para continuar exercitando seus mesmos cenários; nenhuma asserção foi removida ou afrouxada. A suíte final completa passou.

Limite: o modelo ainda pode errar julgamentos semânticos. O contrato final foi reenviado à API na bateria seguinte: resposta correta aprovada, soma errada e evidência ausente recusadas. [Evidências e limites atuais](VALIDACAO_FINAL.md).

## Custo e evidências

Na bateria aqui descrita, antes da finalização, foram 24 chamadas e reserva preventiva US$ 1,944. O registro foi preservado integralmente; o pedido posterior para terminar autorizou um novo lote de três revisões menores dentro dos mesmos US$ 2. Totais atuais e memória de cálculo em [VALIDACAO_FINAL.md](VALIDACAO_FINAL.md).

Contagens, tentativas vermelhas e verdes, hashes das fontes finais e resultados do supervisor: [CORRECOES_LIVE.json](CORRECOES_LIVE.json). O relatório anterior [LIVE_API_2026-10-18.md](LIVE_API_2026-10-18.md) permanece como evidência histórica das falhas. Fontes de teste, scripts, bancos e logs fictícios ficaram nas pastas indicadas no JSON sob `C:\Windows\Temp\auren-correcoes-c704711e41bd461887318de7ea40b7b6`.

## O que não foi testado

tarefas de horas/dias; hardware/voz; perfis, arquivos ou aplicativos pessoais; escrita real; rotinas com efeito real; fábrica global com bancos pessoais; avaliação universal de cálculos e textos. Nenhum `.env`, banco ou log pessoal foi aberto. Perfil e fontes copiados para diretórios temporários; credencial somente herdada do ambiente; supervisor Windows preservado. Não houve alteração do runner ou de suas políticas.
