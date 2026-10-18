# Validação final das correções Live

**A pendência da PR #160 foi concluída: três testes com o contrato final do revisor passaram na API real, sem falhas.** Não houve nova mudança no código de produção. O código validado é `35ee8596573099a0fa8fd5bc26b3e069bfd8aa1c`; o commit posterior contém apenas documentação e evidências.

## Resultado real

| Caso | Resultado da API | Decisão do Auren |
| --- | --- | --- |
| Dois arquivos lidos; códigos corretos e soma 18 | answer_status=verified; todas as etapas com referências válidas | Conclusão aceita |
| Mesmas leituras; resposta alterada para soma 99 | answer_status=failed, mesmo com etapas verified | Conclusão recusada |
| Evidência da segunda leitura retirada | answer_status=pending; segunda etapa pendente | Conclusão recusada |

Foram usados o provider OpenAI e o validador de conclusão existentes, sem resposta simulada ou pós-processamento para forçar aprovação. O modelo foi `gpt-5.6-luna`. Os casos negativos exigiam uma decisão estruturada de recusa; erro de transporte, resposta incompleta ou JSON inválido não contavam como aprovação do teste.

As evidências vieram exclusivamente do banco fictício criado pela bateria anterior, com duas leituras reais de TXT temporários. Nesta validação final não houve execução de ferramentas ou novas ações no computador: três revisões diretas do snapshot pelo provider. A retomada completa do Harness já havia terminado corretamente no Live anterior; os controles de leitura/inspeção negadas também já haviam sido verificados com os executores reais configurados. Não confundir essas verificações diferentes.

## Orçamento preservado

O proprietário autorizou até US$ 2 e pediu concluir depois do teto anterior. Foi preparado um **novo lote de somente três revisões**, com entrada máxima de 10.000 bytes e saída máxima de 600 tokens por chamada, em vez dos limites maiores do lote anterior. O código do Auren, seus guards e critérios dos testes não foram alterados. Sem retry automático.

A reserva usa as mesmas tarifas de segurança anteriores, superiores às publicadas: US$ 1 por milhão de tokens de entrada e US$ 6 por milhão de saída. Com limite de texto de 10.000 bytes, margem adicional de 2.000 tokens e saída de 600 tokens, cada chamada reservou US$ 0,0156 antes do envio. As três adicionaram US$ 0,0468 à reserva anterior US$ 1,944: **reserva acumulada US$ 1,9908, abaixo dos US$ 2**. Todas as 24 entradas anteriores e suas reservas foram preservadas, sem reembolso da reserva ou reinício da contagem. Novo lote documentado, chamadas 25–27.

Total acumulado informado pela API: **27 chamadas, 73.870 tokens de entrada e 1.984 de saída**. Estimativa conservadora acumulada **US$ 0,0208483**, cobrando toda entrada como gravação de cache e saída normal; não é conferência da fatura. Os preços oficiais consultados foram US$ 0,20 por milhão de entrada, US$ 1,20 de saída e gravação de cache a 1,25 vezes entrada. [Documentação oficial OpenAI](https://developers.openai.com/api/docs/models/gpt-5.6-luna).

## Evidências e regressões

Supervisor Windows terminou normalmente, código zero, em **11,31 segundos**. Cópia de fontes, perfil/HOME/TEMP fictícios, sem ler `.env`, logs, bancos ou arquivos pessoais. Credencial herdada do ambiente, sem ser gravada ou exibida. Nenhuma confirmação positiva automática, alteração de runner, hardware/voz ou main.

Decisões completas, parâmetros do novo lote, orçamento, hashes das fontes e dos scripts: [VALIDACAO_FINAL.json](VALIDACAO_FINAL.json). Artefatos brutos e scripts de validação permanecem em pasta temporária, identificada pelo diretório `phase5-final-contract-20261018-01` sob a raiz de evidências usada nas baterias anteriores. Todas as fontes de produção foram comparadas à versão `35ee859` e à cópia testada. As tentativas reprovadas em [CORRECOES_LIVE.json](CORRECOES_LIVE.json) e [LIVE_API_2026-10-18.json](LIVE_API_2026-10-18.json) permanecem históricas; seus campos de pendência descrevem o momento daquelas baterias.

Regressão já aprovada no código final: **1.069 testes locais aprovados/oito ignorados**, CI Windows **1.077 aprovados**, CI Linux **1.033 aprovados/44 ignorados**, zero falhas. [Run do código 39133992031](https://github.com/Yamatosemj/aurenOFC/actions/runs/39133992031). Nenhum código mudou nesta finalização, portanto não foi repetida a suíte local. O CI do HEAD documental final deve ser conferido na PR, sem atribuir a ele um run de outro SHA.

## Encerramento e limites

As correções F5-LIVE-001/002 e a validação pendente do contrato final estão concluídas no escopo testado. Os critérios não foram reduzidos. PR #160 permanece em rascunho para revisão; nenhuma PR foi mesclada e main está intacta.

Isso não demonstra funcionamento universal do Auren. Permanecem fora do teste: tarefas de horas/dias, voz/hardware, arquivos/aplicativos pessoais, escrita real, rotinas com efeitos reais, fábrica global usando bancos pessoais e julgamento correto de todo texto ou cálculo possível. O revisor continua sendo um modelo sujeito a erro; três casos aprovados não garantem qualidade geral. Esses limites estão registrados e não representam uma nova falha ou tarefa iniciada nesta finalização.
