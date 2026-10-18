# Desenvolvimento sequencial do Auren

As mudanças estão em branches e PRs separadas. **Nada foi mesclado à main.** O trabalho avançou somente depois dos testes locais e do CI da fase anterior passarem.

## O que mudou

- **Fase 0 — base:** as versões das PRs #152 e #153 foram reconciliadas na [PR #154](https://github.com/Yamatosemj/aurenOFC/pull/154), mantendo a confirmação para abrir programas por caminho. A verificação de encerramento dos processos dos testes precisou de um ajuste adicional na Fase 1.
- **Fase 1 — salvar objetivos:** o Auren guarda objetivo, plano, passos, estado e histórico. Depois de uma interrupção, não repete uma ação cujo resultado ficou desconhecido. [PR #155](https://github.com/Yamatosemj/aurenOFC/pull/155).
- **Fase 2 — continuar e conferir:** continua o mesmo objetivo em pontos seguros, preserva os limites de execução e pede permissões novas. Antes de dizer que terminou uma tarefa composta, confere evidências das etapas. Pode tentar uma recuperação limitada quando falta uma etapa. [PR #156](https://github.com/Yamatosemj/aurenOFC/pull/156).
- **Fase 3 — acompanhar rotinas:** uma rotina começa como rascunho e precisa de autorização explícita. Tem prazo, quantidade e ações limitadas; pode ser revogada. Uma interrupção com resultado incerto não dispara a mesma rotina de novo automaticamente. [PR #157](https://github.com/Yamatosemj/aurenOFC/pull/157).
- **Fase 4 — mostrar e controlar:** o Chrome mostra tarefas e rotinas; o Tk mostra tarefas. É possível acompanhar estado, pausar, cancelar e retomar pelo mesmo Auren. O cadastro de rotina é separado da autorização. [PR #158](https://github.com/Yamatosemj/aurenOFC/pull/158).
- **Fase 5 — integração:** um objetivo com 16 etapas foi interrompido após oito e terminou em outro processo, sem duplicação. Uma queda depois de um efeito deixou a retomada bloqueada. A interface real foi exercitada com dados e modelo fictícios. O Live completo com a API real continua pendente.

## O que os testes realmente comprovaram

Os testes usam bancos e arquivos temporários. Também usam processos reais, comunicação local e a interface real em um navegador de teste isolado. A execução final da interface passou em **oito verificações**, incluindo negação de uma confirmação e pausa persistida. Nenhuma confirmação positiva foi aprovada automaticamente pelo script de navegador.

As contagens completas, as falhas encontradas e as evidências estão nos [relatórios por fase](CICLO_DESENVOLVIMENTO.md) e nas respectivas PRs. As falhas anteriores foram preservadas; não se retirou proteção ou afrouxou teste para obter aprovação. Teste com resposta de modelo simulada não comprova que o modelo real planejará e verificará corretamente.

| Fase | Passaram localmente | Passaram no Windows do GitHub | Passaram no Linux do GitHub |
| --- | ---: | ---: | ---: |
| 0 | 978 | 986 | 945 |
| 1, após ajuste adicional | 1014 | 1022 | 978 |
| 2 | 1036 | 1044 | 1000 |
| 3 | 1047 | 1055 | 1011 |
| 4 | 1055 | 1063 | 1019 |
| 5 | 1057 | Conferir CI final na PR | Conferir CI final na PR |

As execuções finais locais tiveram zero falhas e oito testes ignorados por limitações de links simbólicos do ambiente. O CI final das Fases 0 a 4 passou sem falhas; Windows não ignorou testes, Linux ignorou 41 na Fase 0 e 44 nas demais. Os conjuntos se sobrepõem: não somar as linhas. A Fase 5 local levou 62,50 segundos, além dos oito controles da interface. O CI final da Fase 5 é conferido separadamente no SHA publicado.

## O que ainda falta

- Definir **cenários e orçamento máximo** para testar com a API real. Essas chamadas não foram executadas sem orçamento.
- Validar qualidade do planejamento/revisor real, custos, latência, tarefas de horas/dias e uso humano das telas.
- A janela Tk não tem o formulário de rotinas; ele está no Chrome. A agenda não roda com o aplicativo fechado nem em outra conversa não selecionada.
- Pausa e cancelamento não cortam uma ação ao meio nem desfazem o que já aconteceu. Passos incertos exigem investigação; não há promessa de retomada automática de toda queda.
- O banco guarda texto sem criptografia ou exclusão automática por prazo. Não houve importação de dados pessoais, teste de hardware/voz ou alteração do runner instalado.

O ciclo não está integralmente validado em uso real. As mudanças estão disponíveis para revisão; a pendência de orçamento impede concluir a parte paga do Live com segurança.
