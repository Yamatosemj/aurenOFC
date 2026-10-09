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

## Windows real: estado atual

**Preparado, mas não ativado nem validado na máquina.**
O template está em [auren-windows-live.yml.template](../.github/runner-templates/auren-windows-live.yml.template);
essa localização/extensão não é executada pelo Actions.

A inspeção confirmou que testes_auren_live.py pode alterar volume, clipboard, janelas, mouse e navegador,
e que L4/L5 podem consumir API. TESTAR_AUREN.bat tem pause e não é adequado para CI;
o template chama o Python diretamente e conserva o código de saída e o relatório do runner.
L3 está reservado e L5 não é oferecido neste primeiro template.

O repositório é público. **Não registrar o Windows pessoal como runner de aurenOFC.**
Um guard em um workflow não protege contra outro workflow malicioso.
[GitHub: uso seguro de runners](https://docs.github.com/en/actions/reference/security/secure-use)
e [environments não isolam runners](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments).

## Validação obrigatória antes da ativação

1. Revisar o SHA exato de Auren que será testado: runner live, módulos importados, ferramentas,
   política de permissões, plugins e dependências. Revisar também os SHAs das actions do template.
   O SHA deve ser de código confiável; o formato de 40 caracteres não comprova segurança.
   Existem PRs de segurança em aberto na inspeção inicial; elas não são incorporadas automaticamente.
2. Usar VM Windows descartável com snapshot, usuário sem administrador, sem pastas/clipboard compartilhados,
   contas pessoais, chaves SSH, tokens GitHub persistentes ou acesso a arquivos pessoais.
   Para áudio/hardware físico, preferir um Windows/usuário de teste dedicado; uma conta separada sozinha
   não isola toda a máquina. Decidir os dispositivos e efeitos permitidos antes de testar.
3. Confirmar que os logs selecionados não revelarão dados pessoais. O template envia apenas live.log e
   RESULTADO_TESTE_AUREN.txt para o repositório privado; não envia todo logs/, screenshots ou memória.
   Mesmo logs privados podem conter informação sensível; revisar os dados usados no teste.
4. Criar repositório **privado de controle**, acessível somente ao responsável, sem PRs externos.
   Copiar o template como .github/workflows/auren-windows-live.yml na main desse repositório.
   Restringir alterações da main e acesso administrativo. Labels não são uma fronteira de segurança.
5. Criar environment auren-windows com branches permitidas apenas main e required reviewer.
   Não habilitar prevent self-review se só existir um responsável que precisa disparar e aprovar.
   Se o plano do GitHub não oferecer essas proteções no repo privado, manter desativado e definir
   outro mecanismo de aprovação antes de continuar. A existência do environment sozinha não exige aprovação.
6. Preparar dentro do ambiente isolado Git, PowerShell 7, Python 3.13 e
   C:\auren-test-env usando venv; instalar as dependências revisadas de requirements.txt.
   Instalar Chromium do Playwright para os escopos que usam navegador.
   Conferir a disponibilidade de desktop interativo e das dependências Windows exigidas pelo SHA revisado.
   Não instalar automaticamente dependências remotas no workflow live.
7. Somente depois dessa revisão, obter o runner oficial em Settings → Actions → Runners do
   **repo privado**, validar o SHA-256 informado pelo GitHub e registrar com --ephemeral e
   label auren-isolated. Não instalar como serviço: iniciar run.cmd na sessão interativa de teste,
   sem privilégios de administrador. Token de registro é temporário e não deve ir para arquivos versionados.
8. No repo privado definir AUREN_REVIEWED_SHA com o SHA completo aprovado e, por último,
   AUREN_WINDOWS_ENABLED=true. Para L4, criar AUREN_TEST_API_KEY no environment,
   usando projeto/chave exclusivos e limites/alertas de gasto. Não usar a chave pessoal principal.
   Começar com L0, depois L2; aprovar L4 somente após avaliar efeitos e custo.

O workflow aceita apenas dispatch manual na main por seu proprietário, verifica repo privado,
habilitação explícita e SHA fixo, e exige o environment antes do job local.
Não aceita comandos arbitrários nem branches de PR para checkout do Auren.
A chave de teste é entregue somente no escopo L4.
L0 valida descoberta; L2 inclui L0/L1 e testes reais locais; L4 inclui L0/L1/L2 e modelo real.
Esses controles reduzem risco, mas não substituem a revisão de todo código que será executado.

Após cada job, encerrar o runner e reverter/recriar a VM; --ephemeral remove o registro após um job,
mas **não limpa a máquina**. Timeout/cancelamento pode deixar aplicativos/subprocessos abertos.
Cada nova execução precisa de nova VM/registro efêmero. Automatizar esse ciclo só depois da primeira
validação, guardando credenciais de provisionamento fora do ambiente de teste.

As etapas de registro, permissões do Windows, escolha de isolamento e eventual chave de API
precisam da participação do dono da máquina. Nada disso foi executado por esta mudança.
