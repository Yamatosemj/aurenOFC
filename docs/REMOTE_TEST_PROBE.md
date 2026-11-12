# Sonda de teste remoto (temporaria)

Esta PR existe apenas para validar o fluxo GitHub -> runner Windows pessoal -> pytest -> logs no GitHub.

- Nenhum codigo de producao ou teste foi alterado.
- O workflow manual de controle remoto deve usar `operacao=testar_pr` e `camada=pytest`.
- O teste deve acontecer em checkout separado; a instalacao principal do Auren nao e atualizada.
- Verificar que o resultado e os artefatos `pr-result.json`, `pr-test.log` e `pytest.xml` aparecem no GitHub Actions.
- Nao mesclar esta PR. Fechar depois que a verificacao remota for confirmada.
