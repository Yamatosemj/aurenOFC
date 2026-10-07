# Prompt-base do Auren

> Você vai me ajudar a evoluir o Auren (assistente desktop/voz para Windows, em Python). Regras:
>
> 1. Leia AUREN_STATE.md e README.md antes de qualquer coisa. Se precisar de um arquivo que você não viu, peça; não invente.
> 2. Uma tarefa por vez. Qualquer ideia fora do escopo vira item de backlog no AUREN_STATE.md, nunca implementação silenciosa.
> 3. Toda ação passa por Router → Dispatcher → Contrato → Permissão → Ferramenta → ToolResult. Não crie caminho paralelo de execução. Conteúdo de web e de plugins é dado não confiável.
> 4. Proibido shell=True, eval e exec. Dependência nova só com versão fixada (existe teste de pins) e, se for opcional, em um requirements separado.
> 5. O Mark-LV (FatihMakes) é referência de IDEIA. A licença é CC BY-NC 4.0: leia o arquivo para entender o problema e os casos-limite, depois escreva do zero no estilo do Auren (nomes em português, ToolResult). Não copie código nem comentários.
> 6. Entregue sempre: arquivos criados ou alterados completos, testes novos, o comando para rodar (py -m pytest -q), a atualização do AUREN_STATE.md e a Nota de passagem preenchida.
> 7. Funções públicas novas ganham docstring de 3 linhas: por que existe, como funciona, quanto custa.

## Regra de uso

Este arquivo é o texto de abertura para novas conversas sobre o Auren. A tarefa concreta deve continuar sendo lida do AUREN_STATE.md e do trabalho em andamento; não substitui a fonte de verdade do repositório.

## Nota de passagem

> Tarefa concluída: (número e nome)
> Arquivos criados/alterados:
> Decisões tomadas (e por quê):
> Testes: (comando, nº de testes antes e depois, resultado)
> Ficou pendente / virou backlog:
> Próxima tarefa: (número)

## Portão de saída

1. `py -m pytest -q` verde, com mais testes do que antes.
2. Os testes listados na tarefa existem e falhariam se a funcionalidade fosse removida.
3. AUREN_STATE.md atualizado na mesma mudança (versão, tarefa atual, backlog).
4. Se a tarefa mexeu em Browser ou Windows, rodar manualmente `python testes_auren_live.py --rapido`.
5. Nota de passagem preenchida e salva em `docs/NOTAS_DE_PASSAGEM.md`.
