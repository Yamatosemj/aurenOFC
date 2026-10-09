# Controle manual do Auren pelo celular

Este controle opera no repositório **privado** `Yamatosemj/aurenOFC`, sem atualização periódica. O PC precisa estar ligado, online, com sessão Windows ativa e self-hosted runner online.

**Verificação real (2026-10-09):** a operação `atualizar_main` foi concluída com sucesso no runner Windows, conforme [execução #37890091132](https://github.com/Yamatosemj/aurenOFC/actions/runs/37890091132). Esta alteração documental serve também como teste de uma nova atualização remota. **Testar PR por número ainda requer uma validação separada no PC.**

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
