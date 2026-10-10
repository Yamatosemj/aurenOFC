# Controle manual do Auren pelo celular

Este controle opera no repositório **privado** `Yamatosemj/aurenOFC`, sem atualização periódica. O PC precisa estar ligado, online, com sessão Windows ativa e self-hosted runner online.

**Verificação real (2026-10-09):** a operação `atualizar_main` foi concluída com sucesso no runner Windows, conforme [execução #37890091132](https://github.com/Yamatosemj/aurenOFC/actions/runs/37890091132). Esta alteração documental serve também como teste de uma nova atualização remota. **Testar PR por número ainda requer uma validação separada no PC.**

## Autorizacao unica no Windows (novos testes por chat)

Ja existe o workflow que aceita comentario em PR; para o runner permitir esses testes, o proprietario precisa executar **uma unica vez**, depois de atualizar a main, o instalador `scripts/instalar/AUTORIZAR_TESTES_CHAT.ps1` no seu proprio Windows. Ele identifica o `before-job.ps1` antigo, cria `before-job.pre-chat.bak`, instala `chat-control-functions.ps1` e `chat-control-approval.json` ao lado dele, sem mexer no fluxo manual existente.

O controle local recusa executores administradores, emergencia ativa, comentario de terceiros, PRs de forks, workflows modificados, SHAs diferentes e reexecucoes da tentativa do runner. Confere o **blob exato do arquivo workflow** aprovado no GitHub (nao somente branch `main`), de modo que futuros commits na `main` nao exigem reconfiguracao se o workflow continuar exatamente igual. O validador hospedado tambem utiliza commit imutavel.

Para atualizar o clone principal configurado anteriormente, rode o instalador apenas apos um `git pull --ff-only` bem-sucedido. Se a instalacao responder que o hook local diverge do esperado, **pare**: nao force substituicao nem remova a politica. Esta automacao so aceita pytest sem chave de API e baixa a versao para uma pasta de testes, preservando o Auren em uso.

Apos instalar, o assistente pode comentar `AUREN_TESTE_V1 pytest SHA40` em uma PR e recuperar o relatorio sem precisar do usuario entrar no GitHub. **Ainda precisa de prova end-to-end no seu Windows real para ser declarada concluida.** O PC continua precisando estar ligado, conectado e com o runner online durante cada teste.

## Testes enviados pelo chat — configuracao em andamento

Um usuario nao precisa abrir o GitHub: o assistente, via GitHub conectado, publica na conversa de uma **PR aberta e revisada** o comentario exato `AUREN_TESTE_V1 pytest <SHA40>`. O workflow da branch padrao `.github/workflows/auren-chat-tests.yml` recebe `issue_comment`, valida a autoria do proprio dono, projeto privado, PR interna, base `main`, SHA do HEAD congelado, e usa um controlador Windows fixado em commit imutavel.

Quando autorizado na politica **local**, o runner baixa a PR para `pr-checkout` (sem atualizar o clone principal), roda pytest sob watchdog por no maximo 20 min e publica `pr-result.json`, `pr-test.log` e `pytest.xml`. Esses dados podem ser inspecionados pelo assistente via GitHub, sem links/formularios para o usuario. `OPENAI_API_KEY` nao e liberada nessa bateria.

**Ainda nao operacional:** o hook `%USERPROFILE%\\auren-remote\\policy\\before-job.ps1` bloqueia novas familias de workflow por seguranca e so pode ser examinado e alterado no proprio notebook; e necessaria aprovacao local pontual do novo fluxo, mantendo as verificacoes de usuario sem admin, projeto, evento, workflow e permissoes. Nunca desative o hook para fazer o teste passar.

O comentario pertence a uma PR; o assistente identifica o numero e SHA antes de comentar. Não aceita texto livre no shell, nem faz `git pull` automático na instalacao de uso diario. O workflow anterior `auren-update-pc.yml` permanece intacto e continua reservado ao uso manual enquanto a migracao e validada.

## O que foi preparado no GitHub

Workflow: `.github/workflows/auren-update-pc.yml` (**Auren - controle remoto do PC**).

Para uma execução manual no GitHub Actions, selecione a branch **`ci/remote-update-control`**, que contém o código de controle fixo e não deve acompanhar as alterações frequentes da `main`.

- `operacao=atualizar_main`: não precisa informar PR. Executa `git pull --ff-only origin main` na instalação principal configurada no PC. Exige branch local `main`, origin esperado e nenhuma alteração rastreada. Não executa testes e não força/reset o checkout. Retorna SHA antes/depois ou causa da falha.
- `operacao=testar_pr`: informe somente o **número da PR**. Um job hospedado pelo GitHub valida que a PR está aberta, não é draft, aponta para `main` e pertence a este mesmo repositório (não fork). Congela o SHA no início, depois faz checkout para a pasta **pr-checkout** do runner, separada da instalação principal. O nome da branch é irrelevante. O job usa `pr_job.py` e o watchdog do branch de controle para rodar `pytest` no Windows real e guardar `reports/pr-result.json`, `reports/pr-test.log` e `reports/pytest.xml`.
- `camada=pytest` é o padrão para testes de PR. `L0`, `L1`, `L2`, `L4`, `L5` e `ALL` são opcionais. Ao selecionar `L4`, `L5` ou `ALL`, forneça o SHA completo revisado no campo `sha_aprovado`; a chave API não é adicionada automaticamente às opções mais simples. Testes live podem controlar janelas, mouse, teclado e consumir API. O watchdog impõe limite absoluto de 20 minutos, 120 segundos sem saída, 16 MiB de log e um mutex compartilhado com live existente. Testes não são repetidos automaticamente.

O resultado fica na página da execução do GitHub Actions (sucesso, falha ou timeout). Os relatórios privados são retidos por 7 dias. O workflow só roda por despacho manual do proprietário em repositório privado e na branch de controle.

## Configuração local (para instalação ou recuperação)

Este repositório contém **somente o código do GitHub**. A política real do runner está **fora do GitHub**, no Windows, e aceita apenas workflows específicos e commits fixados. A operação de atualizar `main` já foi validada em Windows; os passos abaixo documentam a configuração necessária em caso de reinstalação ou recuperação:

1. Revisar este workflow e o arquivo `remote_tests/pr_job.py` com atenção. Aprovar a branch estável de controle `ci/remote-update-control` pelo seu SHA exato na política `%USERPROFILE%\auren-remote\policy\before-job.ps1`, sem retirar as regras de repositório privado, proprietário, não-admin e dispatch manual. Não permita qualquer branch/SHA arbitrário.
2. Criar `%USERPROFILE%\auren-remote\policy\checkout-path.txt` contendo apenas o caminho absoluto do clone principal real do Auren que está na `main`. Não adivinhar o caminho.
3. Confirmar que `git.exe`, Git Credential Manager autenticado e o venv Python em `%USERPROFILE%\auren-remote\venv` estão disponíveis ao usuário não-administrador do runner.
4. Após a PR que registra o workflow na `main` ser mesclada, testar primeiro `operacao=atualizar_main` com clone de laboratório ou `testar_pr` em `pytest` numa PR revisada. Revisar logs, sem fornecer senhas/token no chat.

**Importante:** o GitHub NÃO tem acesso direto aos arquivos de política do Windows. Não alterar ou contornar os bloqueios locais por conta de um workflow GitHub. O SHA da branch de controle deve permanecer estável após a aprovação local; se mudar, uma nova aprovação será necessária.

Executar testes de PR no mesmo Windows de uso diário **não é sandbox**: código de testes pode ter acesso aos dados e permissões do usuário Windows. Use somente PRs de origem confiável e revisada, preferencialmente num ambiente dedicado. Para verificar código não confiável, use os runners hospedados no GitHub em vez do runner pessoal.
