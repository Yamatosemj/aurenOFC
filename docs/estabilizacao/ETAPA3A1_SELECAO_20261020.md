# Etapa 3A.1 — Integridade da seleção no navegador

Candidata local derivada da #175 (`bf852d5`), sem publicação ou merge. Escopo:
somente seleção de `clicar_elemento` e `preencher_elemento`. Os demais achados
da auditoria 3A continuam pendentes.

## Causa e correção

O schema exigia `indice`, descrito como iniciado em 1, mas não declarava mínimo.
O executor usava `max(1, indice)` e parâmetros Python com padrão 1: zero,
negativos e chamadas diretas sem índice podiam atingir a primeira ocorrência.
Além disso, uma ocorrência ausente em uma busca exata podia cair em busca
parcial ou papel/atributo menos prioritário e atingir outro alvo.

As duas ferramentas agora declaram `minimum: 1`. A resolução exige inteiro
explícito (não booleano), alvo textual não vazio e ocorrência existente.
Argumentos inválidos falham antes de obter/abrir página. O primeiro conjunto
não vazio fixa a seleção: índice fora dele falha, sem ampliar a busca.
Falhas de seleção retornam `ToolResult.failure`, `invalid_selection`; argumentos
rejeitados no Dispatcher continuam usando `contract_error`, antes de permissões.
Nenhuma política de PermissionManager foi alterada.

## Contrato preservado

Ocorrências visíveis começam em 1, na ordem do locator Playwright dentro do
primeiro conjunto correspondente. Duplicatas são selecionáveis com índices
explícitos 1, 2 etc.; ausência do índice não resolve a ambiguidade automaticamente.
Mantêm-se prioridade de atributos exatos para preenchimento, papéis por nome
exato, depois parcial e por fim label/placeholder/texto, quando os conjuntos
anteriores estão vazios. Não se concatena o resultado de buscas distintas.

Zero continua significando **aba ativa** em `fechar_aba`; os demais índices de
abas e os índices de UIA não foram alterados. Uma rejeição de preenchimento não
é prova de que o campo aceitaria texto: compatibilidade do controle e exceções
de execução continuam sob os comportamentos existentes.

## Validação e limites

`tests/test_browser_selection_integrity.py` cobre contratos/Dispatcher,
PermissionManager real com confirmação roteirizada e executores com DOM falso:
zero, negativos, tipos incorretos, ausência, duplicatas, faixas, atributos,
prioridade, nomes parciais, alvos inexistentes e elementos ocultos. Execução:

```powershell
python -m pytest -q tests/test_browser_selection_integrity.py
```

O relatório externo `etapa3a1/RELATORIO_ETAPA3A1.md` registra SHA, comparação
vermelho/verde, suíte offline selecionada e contraprovas em Chromium headless
com DOM real, perfil descartável e requisições bloqueadas. Os scripts externos
redirecionam dados/logs e bloqueiam API, desktop nativo e escrita no checkout.
Não equivalem a sandbox do sistema operacional.

Sem API, desktop pessoal, janelas visíveis, Windows/UIA real ou CI desta
candidata. DOM que muda entre resolução e ação e identificação semântica de
intenção permanecem limites; estes testes não provam segurança em todo site.
Não houve correção dos outros achados, avanço à etapa 3B/4 ou autorização
implícita para publicar a branch.
