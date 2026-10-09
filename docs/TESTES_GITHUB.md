# Testes do Auren pelo GitHub

## Pelo celular

No navegador do celular, entre no GitHub e abra [Auren - testes manuais](https://github.com/Yamatosemj/aurenOFC/actions/workflows/auren-manual-tests.yml).
Toque em **Run workflow**, escolha a branch (normalmente main) e confirme.
Se o botão não aparecer no aplicativo, use o navegador com a versão desktop da página.

A execução roda toda a suíte de tests/ com Python 3.13 em ubuntu-latest e windows-latest do GitHub.
Não usa chave de API, runner do seu computador nem a bateria live.
Abra a execução para ver o resumo por sistema, as falhas nos passos e os artifacts:
- pytest.xml: relatório JUnit;
- pytest.log: saída completa, falhas e skips;
- install.log: instalação, inclusive falhas anteriores aos testes;
- dependencies.txt: versões instaladas.

Os artifacts ficam por 14 dias; os logs dos passos também ficam no GitHub conforme a retenção do repositório.
Falhas mantêm o job vermelho. Cancelamento forçado ou perda do runner pode impedir o upload.
Os workflows anteriores continuam preservados. O novo workflow também roda em PR que altera seu próprio arquivo, para validar a automação antes de integrá-la.
Não há mudanças no código do Auren.

## Windows local: configuração em andamento

O repositório foi confirmado **privado** nesta inspeção (2026-10-09).
O workflow existente de pytest continua usando exclusivamente os runners do GitHub.
Os workflows de push/pull_request existentes também usam exclusivamente runners do GitHub.

[Auren - verificar conexão Windows](https://github.com/Yamatosemj/aurenOFC/actions/workflows/auren-windows-connection.yml)
é manual, sem inputs, checkout, actions externas, dependências ou código importado do Auren.
Aceita somente a main do repositório privado, acionada ou reexecutada pelo proprietário.
Usa token sem permissões declaradas, timeout de 3 minutos e label auren-isolated.
A única escrita explícita é o resumo da própria execução; o runner também grava seus arquivos operacionais.
O teste verifica Windows/processo de 64 bits e publica confirmação nos logs e no resumo,
sem listar ambiente, nomes de usuário, caminhos pessoais, credenciais ou identidade do computador.

**Estado: workflow preparado; runner não instalado/registrado; conexão não testada.**
A ferramenta local falhou antes de iniciar comandos PowerShell e CMD com
helper_unknown_error: setup refresh had errors. Isso impede inspecionar autenticação local,
instalar dependências, verificar checksum do runner, registrar ou iniciar o processo.
A conexão GitHub disponível permite editar arquivos, mas não oferece ferramentas para
registrar runners, alterar configurações administrativas ou disparar workflow_dispatch.

## Testes reais: bloqueados

O [template live](../.github/runner-templates/auren-windows-live.yml.template)
permanece fora dos workflows ativos e agora tem também um bloqueio literal no job live.
Mesmo copiar o template e definir variáveis não executa esse job.
L2/L4 podem controlar desktop, volume, clipboard, janelas, navegador e arquivos; L4 pode usar API.
Nem o runner live, nem a suíte pytest inteira devem ser executados no PC pessoal sem
revisar os efeitos dos módulos e dos testes no SHA aprovado.
Ações de mouse, teclado, navegador e alterações de arquivos dependem de autorização explícita posterior.
Preparar dependências e arquivos operacionais do runner foi autorizado; executar esses efeitos pelo Auren não foi.

## Próximas operações do agente após restabelecer o executor local

- Inspecionar ferramentas, usuário/privilégios e autenticação GitHub existente sem imprimir tokens.
- Validar controles do repositório privado, colaboradores e workflows antes de registrar.
- Baixar o runner oficial e verificar seu SHA-256; instalar em pasta dedicada ao usuário,
  fora de System32, sem serviço administrador e sem credenciais em arquivos versionados.
- Definir como impedir que outros workflows ou PRs alcancem o runner, além dos guards
  deste workflow. Labels não fornecem isolamento; não declarar restrição configurada sem verificá-la.
- Iniciar somente o runner autorizado para a conexão inofensiva; verificar logs/resumo no GitHub.
- Preparar ambiente separado do Auren e dependências revisadas; continuar com testes live bloqueados.

Runner de repositório pessoal não tem automaticamente as restrições por workflow dos
[runner groups de organização/enterprise](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/manage-access).
A instalação permanece pendente até validar o mecanismo efetivo de restrição, os privilégios
e a proteção do Windows. Usar --ephemeral quando apropriado não limpa o computador após o job.

O usuário pediu execução direta pelo agente. Não há comandos para copiar e colar nesta configuração.
Se for necessária autenticação ou permissão adicional, o agente solicitará somente a aprovação correspondente.
