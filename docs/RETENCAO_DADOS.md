# Retenção e esquecimento

O Auren só executa a limpeza descrita aqui quando o proprietário a pede. Feche o Auren antes de usar. Nada é apagado ao instalar esta correção ou abrir o programa.

| Classe | Prazo usado pela limpeza manual |
| --- | --- |
| Fatos salvos | Até esquecer explicitamente a chave |
| Conversas | 30 dias |
| Estratégias | 90 dias desde a atualização |
| Rastros de tarefas concluídas | 30 dias desde o término |
| Registros `.log` e `.txt` em `logs/` | 30 dias desde a última alteração |
| Capturas `screen_*.png` em `runtime/screenshots/` | 7 dias desde a última alteração |

Primeiro veja as quantidades, sem apagar:

```powershell
python -m core.retention --raiz "C:\caminho\do\AUREN"
```

Depois de revisar, o comando abaixo confirma a exclusão dos itens vencidos:

```powershell
python -m core.retention --raiz "C:\caminho\do\AUREN" --aplicar
```

O caminho precisa ser indicado explicitamente. A limpeza atua somente nos bancos e pastas conhecidos dentro dessa raiz e recusa caminhos com links ou junctions. Ela não cria bancos ausentes. Tarefas sem data de término são preservadas. Remover rastros vencidos também remove seus detalhes.

“Esquecer uma memória” remove somente o fato salvo com a chave exata. Não apaga frases equivalentes em conversas, estratégias, rastros, registros, backups ou OneDrive; a resposta dessa ferramenta passa a explicar esse limite. A limpeza manual resolve a retenção das classes listadas, mas não procura todas as cópias de uma informação nem equivale a apagar com segurança os bytes do disco. Backups e sincronização precisam de tratamento próprio.

Os prazos são a decisão conservadora adotada nesta manutenção autorizada. Não foi programada limpeza automática. Não execute a limpeza enquanto o Auren escreve nesses arquivos. Corridas hostis de troca de diretórios não foram validadas; a recusa de links não é uma garantia contra qualquer processo malicioso no computador.
