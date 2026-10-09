# Auren: testes remotos pelo GitHub

Configurado em 2026-10-09 no Windows local. Repositorio privado confirmado; somente o proprietario aparece como colaborador. Autenticacao existente do Git Credential Manager reutilizada, sem copiar tokens para arquivos versionados.

## Conexao validada

[Execucao real aprovada](https://github.com/Yamatosemj/aurenOFC/actions/runs/37884137457): sucesso. O hook local confirmou processo sem privilegios administrativos antes dos passos. Nenhum modulo do Auren foi carregado.

Pelo celular, abra [Conexao Windows](https://github.com/Yamatosemj/aurenOFC/actions/workflows/auren-windows-connection.yml) no navegador e use Run workflow na main. O PC precisa estar ligado, conectado e com o usuario conectado ao Windows. O runner inicia no login pela tarefa AurenAuthorizedRunner, com RunLevel Limited; nao foi instalado como servico administrador.

## Restricao efetiva

Runner oficial 2.338.0 com SHA-256 verificado contra o digest da release. Instalacao em %USERPROFILE%\auren-remote\runner. Hook externo em policy\before-job.ps1 rejeita o job antes dos passos se evento, repositorio privado, ator, reator, branch, workflow ou SHA nao corresponderem a conexao revisada. Tambem rejeita processo elevado. O commit permitido fica na politica local; mudancas na main exigem revisao e atualizacao local pelo agente. Labels apenas selecionam o runner.

A conta pessoal nao oferece restricao de runner group por workflow. A protecao adotada e local, com SHA fixo, e nao constitui sandbox contra o proprietario/administrador do repositorio ou da maquina. Nao ha gatilhos pull_request nos workflows. CI em push continua exclusivamente nos runners do GitHub. GITHUB_TOKEN da conexao tem permissions: {}; a configuracao padrao do repositorio e read, sem aprovar PRs.

O runner publica automaticamente nome da maquina e caminhos operacionais nos logs privados de inicializacao; o passo de conexao nao lista ambiente nem credenciais. Credenciais internas do runner permanecem somente na instalacao local. Nenhuma chave de API foi adicionada ao GitHub.

## Testes reais preparados e bloqueados

[Auren - Windows real](https://github.com/Yamatosemj/aurenOFC/actions/workflows/auren-windows-live.yml) foi preparado a partir do template existente. O job live conserva if: ${{ false }}. Variaveis, inputs e reruns nao removem esse bloqueio; a politica local tambem rejeita este workflow.

Ambiente Python 3.13 separado em %USERPROFILE%\auren-remote\venv, com requirements.txt, pytest 9.1.1 e numpy 2.5.3. Logs de instalacao e inventario de dependencias ficam na pasta local. Nenhuma suite pytest ou live foi executada no PC. O template usa esse ambiente e PowerShell existente, publica logs selecionados como artifacts privados por sete dias e resumo por execucao.

L2/L4 incluem desktop, mouse, teclado, navegador, volume, clipboard, janelas e arquivos; L4 pode consumir API. Ate L0 grava relatorio: nao foi executado. A liberacao depende de autorizacao explicita do usuario para o escopo, revisao dos efeitos no SHA escolhido e atualizacao da politica local. O workflow continua bloqueado ate essas etapas. Nao e necessario fornecer comandos ao usuario.

## Testes hospedados

[Auren - testes manuais](https://github.com/Yamatosemj/aurenOFC/actions/workflows/auren-manual-tests.yml) continua executando pytest em ubuntu-latest/windows-latest do GitHub. Publica pytest.xml, pytest.log, install.log e dependencies.txt por 14 dias; nao utiliza o PC nem a bateria live.
