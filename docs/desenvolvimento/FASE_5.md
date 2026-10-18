# Fase 5 — validação integrada e limite do Live

Base: Fase 4, `29dd494`, [CI 39130569555](https://github.com/Yamatosemj/aurenOFC/actions/runs/39130569555) aprovado: Windows 1.063; Linux 1.019/44 ignorados. Branch própria `desenvolvimento/fase-5-validacao-integrada`. Main consultada novamente em `70b040d6191237e2f0a291a14b8ea8fb4b78a09d`. Nenhum merge, push para main ou instalação pessoal foi realizado.

**Estado atual: correções e validação pendente concluídas na PR #160. Três testes com o contrato final do revisor passaram na API real; regressão local e CI aprovados.** [Evidências finais e limites](fase5/VALIDACAO_FINAL.md). As baterias anteriores abaixo permanecem históricas.

## Evidência entre processos

Foi acrescentada uma fixture que compõe Harness, TaskManager, PermissionManager e Dispatcher reais, com provider e handlers pessoais fictícios. Não importa a composição global do aplicativo nem abre seus bancos reais.

Um objetivo de 16 etapas gera observações numeradas em arquivo temporário. Após a oitava, o Harness publica checkpoint e pausa. O processo termina com `os._exit(17)`, sem shutdown normal. Outro processo abre o mesmo SQLite e retoma o mesmo objetivo. O arquivo precisa terminar exatamente com `1` a `16`, na ordem e sem repetição; os 16 resultados precisam ficar no histórico, com conclusão verificada e limite original de chamadas preservado. A validação não se baseia na frase do provider fictício.

Outra execução grava um efeito fictício depois de `begin_step` e termina com `os._exit(21)` antes de `finish_step`. O novo processo encontra o passo incerto, recusa a retomada e mantém o arquivo com exatamente um efeito. Não inventa resultado nem apaga o registro para tentar novamente.

Esses dois casos entram na suíte completa e são portáveis. Demonstram tarefa com muitas etapas e retomada real entre processos, **não** estabilidade por horas/dias ou qualidade do planejamento de um modelo real. Falhas de armazenamento, concorrência, orçamento, escopo, recuperação limitada, negação e revogação das fases anteriores continuam na suíte de regressão.

## Interface real em ambiente isolado

O script explícito `remote_tests/phase5_ui_smoke.py` foi executado em cópia de fontes, perfil e arquivos temporários, sem credenciais ou `.env`, sob o supervisor Windows com prazo e contenção da árvore de processos. O servidor, worker, Harness, SQLite, browser e widgets Tk são reais. Modelo e efeitos de ferramentas pessoais são fictícios. Não foi executado `testes_auren_live.py`, API paga, voz, dispositivo ou aplicativo pessoal.

O Chrome instalado recusou o lançamento automatizado. Não foi alterada sua instalação, política ou perfil para contornar a recusa. Foi instalada uma cópia de teste do Chromium/Playwright **somente em pasta temporária**, e o browser foi iniciado com sandbox habilitado e contexto novo. Requisições de página fora da origem exata do servidor 127.0.0.1 eram abortadas; nenhuma foi observada nessa execução. Isso descreve o controle do tráfego de páginas, não uma regra de firewall do sistema. Referências consultadas: [Playwright BrowserType](https://playwright.dev/python/docs/api/class-browsertype) e [Route](https://playwright.dev/python/docs/api/class-route).

Uma primeira execução com o browser de teste encontrou um seletor ambíguo do **script de validação**, entre o histórico e o formulário de rotina. O seletor passou a apontar apenas para o formulário direto. Não foi modificada a aplicação ou relaxada uma exigência para fazê-lo passar. O script passou a registrar progresso parcial, e as tentativas anteriores e seus resultados de encerramento foram preservados.

Na execução final, Chromium 153.0.8010.12, **oito verificações passaram**:

1. Objetivo salvo aparece como texto; um trecho de teste com aparência de HTML não cria imagem nem executa script.
2. Clicar Retomar conclui o mesmo objetivo sem repetir o passo salvo.
3. Cadastro de lembrete fica em rascunho; revogação funciona, sem aprovação automática.
4. Uma confirmação real da interface é negada; o handler fictício não é executado.
5. O progresso mostra WAITING, o botão Pausar solicita pausa e o banco termina em PAUSED depois do passo seguro.
6. Nenhum erro JavaScript de página é observado.
7. Browser/worker fecham, o banco é reaberto e a pausa permanece sem cancelamento pendente.
8. Widgets Tk reais, com janela retirada da tela, mostram a pausa salva e permitem cancelá-la no banco.

Houve quatro chamadas ao **provider fictício**, nenhuma chamada à API, nenhum efeito pessoal e nenhuma confirmação positiva aprovada pelo script de browser. O supervisor terminou normalmente com código zero e confirmou o encerramento da sua árvore. A imagem `fase5/interface_chrome.png` mostra apenas dados fictícios. Tk foi validado por seus widgets, não por aparência física, DPI, foco ou uso humano.

## Resultado e pendências

Contagens da suíte completa, resultados de tentativas, hashes das fontes e artefatos estão em `fase5/RESULTADOS_FASE_5.json` e `fase5/RESULTADOS_INTERFACE.json`. O CI final deve ser registrado na PR no SHA publicado. Não somar os oito controles manuais aos testes pytest como se fossem a mesma bateria.

Suíte completa local final: **1.057 aprovados, zero falhas e oito ignorados**, em **62,50 segundos**. Os oito ignorados exigem links simbólicos indisponíveis neste Windows. A seleção entre processos teve dois aprovados e é parte da suíte completa; a interface isolada teve oito controles aprovados em 12,47 segundos de supervisão.

Após a bateria descrita acima, houve autorização de até US$ 2 e execução com API real: 19 chamadas, estimativa conservadora US$ 0,01538. O orçamento deixou de ser bloqueio; os achados Live impedem aprovar esta fase. Consultar o relatório atual indicado no início.

Para retomar, seguir F5-LIVE-002 e F5-LIVE-001 no relatório atual, preservando o orçamento acumulado e a rota normal de permissões. A sequência foi interrompida devido aos achados; PRs em rascunho e main intacta.
