# Auren: testes remotos pelo GitHub

> **Revisão de 2026-10-10:** este guia conserva o histórico de instalação/Live de 2026-10-09. Uma execução real posterior do comando por comentário na PR #119 está comprovada pelo [run #38085000162](https://github.com/Yamatosemj/aurenOFC/actions/runs/38085000162): validador e Windows aprovados, `PR test: completed; exit=0`. **Isso foi pytest no runner pessoal, sem API; não foi Live.** Consulte o [mapa auditado dos fluxos da Etapa 9](architecture/09-testes-ci-controle-remoto.md) antes de usar instruções históricas. O estado atual do PC/hook não é observável somente pelo GitHub.

Configurado em 2026-10-09 no Windows local. Repositorio privado confirmado; somente o proprietario aparece como colaborador. Autenticacao existente do Git Credential Manager reutilizada, sem copiar tokens para arquivos versionados.

## Conexao validada

[Execucao real aprovada](https://github.com/Yamatosemj/aurenOFC/actions/runs/37884137457): sucesso. O hook local confirmou processo sem privilegios administrativos antes dos passos. Nenhum modulo do Auren foi carregado.

Pelo celular, abra [Conexao Windows](https://github.com/Yamatosemj/aurenOFC/actions/workflows/auren-windows-connection.yml) no navegador e use Run workflow na main. O PC precisa estar ligado, conectado e com o usuario conectado ao Windows. O runner inicia no login pela tarefa AurenAuthorizedRunner, com RunLevel Limited; nao foi instalado como servico administrador.

## Restricao efetiva

Runner oficial 2.338.0 com SHA-256 verificado contra o digest da release. Instalacao em %USERPROFILE%\auren-remote\runner. Hook externo em policy\before-job.ps1 rejeita o job antes dos passos se evento, repositorio privado, ator, reator, branch, workflow ou SHA nao corresponderem aos workflows de conexao/live revisados. Tambem rejeita processo elevado. O commit permitido fica em policy\live-approval.json, junto do estado live_ready validado pelo agente; mudancas na main exigem revisao e atualizacao local pelo agente. Labels apenas selecionam o runner.

A conta pessoal nao oferece restricao de runner group por workflow. A protecao adotada e local, com SHA fixo, e nao constitui sandbox contra o proprietario/administrador do repositorio ou da maquina. Os workflows de **conexão e Windows Live pessoal** não têm gatilhos `pull_request`; são manuais e autorizados. Já a **suíte CI hospedada** em `.github/workflows/auren-file-intelligence.yml` e `.github/workflows/auren-visual-interaction.yml` **tem** gatilhos `push` e `pull_request` em `main` e não usa o Windows pessoal. GITHUB_TOKEN da conexao tem permissions: {}; live tem contents: read; a configuracao padrao do repositorio e read, sem aprovar PRs.

O runner publica automaticamente nome da maquina e caminhos operacionais nos logs privados de inicializacao; o passo de conexao nao lista ambiente nem credenciais. Credenciais internas do runner permanecem somente na instalacao local. Nenhuma chave de API foi adicionada ao GitHub.

## Testes reais autorizados com supervisao

[Auren - Windows real](https://github.com/Yamatosemj/aurenOFC/actions/workflows/auren-windows-live.yml) foi preparado a partir do template existente e liberado com a autorizacao posterior descrita abaixo. Exige acionamento manual pelo proprietario no SHA revisado, validado tambem pela politica local.

Ambiente Python 3.13 separado em %USERPROFILE%\auren-remote\venv, com requirements.txt, pytest 9.1.1 e numpy 2.5.3, mais Chromium do Playwright. Logs de instalacao e inventario de dependencias ficam na pasta local. O workflow usa esse ambiente e PowerShell existente, publica logs selecionados como artifacts privados por sete dias e resumo por execucao.

L2/L4/L5 incluem desktop, mouse, teclado, navegador, volume, clipboard, janelas e arquivos; L4/L5 podem consumir API. Ate L0 grava relatorio. Todas as camadas implementadas foram autorizadas, com limites externos e internos descritos abaixo. Nao e necessario fornecer comandos ao usuario.

## Testes hospedados

[Auren - testes manuais](https://github.com/Yamatosemj/aurenOFC/actions/workflows/auren-manual-tests.yml) continua executando pytest em ubuntu-latest/windows-latest do GitHub. Publica pytest.xml, pytest.log, install.log e dependencies.txt por 14 dias; nao utiliza o PC nem a bateria live.

## Autorizacao live e protecoes (2026-10-09)

O usuario autorizou explicitamente preparar e liberar L0, L1, L2, L4 e L5, exigindo protecoes contra loops e travamentos antes de executar. L3 continua reservada e nao e oferecida. O workflow live substitui o bloqueio literal por validacao manual do proprietario, inclusive triggering_actor, repositorio privado, main e SHA revisado. A politica local permite somente conexao/live no mesmo SHA revisado.

O seletor oferece L0, L1, L2, L4, L5 e ALL. Dependencias entre camadas sao mantidas pelo tester. A opcao verificar_protecoes executa somente fixtures inofensivas, sem carregar Auren nem acessar API ou desktop. O runner verifica isso antes da primeira execucao real.

Protecoes implementadas:
- Supervisor Windows externo inicia Python suspenso, associa a um Job Object e so depois libera sua execucao. Kill-on-close encerra a arvore de processos se houver timeout, cancelamento ou morte do supervisor. Sem matar por nome; apps preexistentes ficam fora do Job Object. Sem permissao de breakaway; maximo de 64 processos e 4 GiB para a arvore.
- Suite: limite absoluto de 20 minutos, 120 segundos sem saida, arquivo de log limitado a 16 MiB. Job do GitHub: 25 minutos para permitir resumo/upload. Sem retries automaticos do workflow; concurrency e mutex local impedem duas suites simultaneas.
- Integracao L4/L5: Job Object adicional, 240 segundos absolutos e 90 segundos sem saida por bateria. Saida parcial fica em reports/integrated-L4.log e integrated-L5.log mesmo se interrompida.
- Modo teste: teto rigido de oito rodadas por tarefa, mantendo os limites existentes de dez acoes, tres falhas consecutivas, duas falhas identicas e tres repeticoes sem progresso.
- API: timeout do SDK de 45 segundos e zero retries no modo teste. O limite externo absoluto cobre operacoes que nao respondam ao timeout do SDK. [OpenAI Docs](https://developers.openai.com/api/reference/python).
- Confirmacao interativa e negada no modo teste: nao trava nem consome o proximo comando roteirizado. A autorizacao da bateria nao transforma automaticamente toda solicitacao de confirmacao do modelo em sim; os testes podem registrar falhas de permissao.
- Cancelar a execucao pelo GitHub interrompe os processos de teste. O agente tambem pode criar %USERPROFILE%\auren-remote\STOP-LIVE: bloqueia novas suites e encerra a atual em aproximadamente 100 ms. O arquivo precisa ser removido explicitamente pelo agente para retomar.

A chave de API ja existente no ambiente do usuario e reutilizada localmente; acesso ao modelo configurado gpt-5.6-luna confirmado sem revelar a chave. Nao foi criada uma nova credencial nem copiada a chave para secrets. Console usa add-mask e os logs supervisionados redigem o valor da chave antes de virar artifacts.

Fixtures verificam timeout silencioso, loop com saida continua, log flood, interrupcao do supervisor, limpeza de filhos no sucesso, stdin roteirizado, parada antecipada e redacao de credencial ficticia. Os testes selecionados de guards, loop owner, permissao, confirmacao e provider foram executados antes da liberacao.

Interrupcao forcada garante encerramento dos processos contidos, mas nao reverte efeitos ja ocorridos, como clipboard, volume ou arquivos; os finally normais tentam suas limpezas. O runner roda na sessao interativa do usuario, sem privilegios administrativos. Resultados nao devem ser interpretados como isolamento de seguranca do desktop.

Pelo celular, use [Windows real](https://github.com/Yamatosemj/aurenOFC/actions/workflows/auren-windows-live.yml), main, camada desejada ou ALL. PC ligado, conectado e usuario conectado. Resultados incluem reports/watchdog.json (motivo, duracao e exit code), live.log, logs parciais integrados e relatorio do tester. Falha e timeout deixam o job vermelho; artifacts selecionados privados ficam por sete dias.

Validacao antes dos testes reais: 68 testes selecionados passaram localmente; as 12 fixtures de seguranca tambem passaram no runner sem elevacao via [GitHub Actions](https://github.com/Yamatosemj/aurenOFC/actions/runs/37885714287), com logs e JUnit publicados. O job de efeitos reais foi ignorado nessa execucao. O agente so marca live_ready=true depois desse resultado.

A primeira bateria ALL terminou normalmente em 1,09 s e publicou [resultado de falha na descoberta](https://github.com/Yamatosemj/aurenOFC/actions/runs/37885861691): 6 PASS/1 FAIL, sem executar camadas funcionais. A checagem UIA ainda apontava para a facade windows.py antiga; foi corrigida para windows_uia.py mantendo todos os tokens obrigatorios, incluindo IsPassword. Tester sincronizado com V47. Dois testes estaticos confirmam descoberta correta e rejeicao do bridge sem protecao de senha; 75 testes selecionados passaram apos essa correcao.

A tentativa seguinte publicou [logs do erro de carregamento](https://github.com/Yamatosemj/aurenOFC/actions/runs/37886027652) e terminou em 2,61 s, sem travar. Cinco aliases privados usados por core.facade nao tinham sido reexportados por tools.windows apos a separacao dos modulos. Os reexports foram restaurados mantendo a identidade das implementacoes nativas. Excecoes de inicializacao das camadas agora tambem geram o relatorio final. Testes de regressao cobrem ambos os problemas; 79 testes selecionados passaram.
