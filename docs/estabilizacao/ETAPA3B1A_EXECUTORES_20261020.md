# Etapa 3B.1A — Validação dos executores nativos diretos

Correção local sobre a candidata #176 (`1cfcbd9`), restrita aos dois achados da
etapa 3B.1. Sem publicação, merge, execução real de desktop ou mudança de política.

## Clique global

`clicar_mouse_windows` posicionava o cursor antes de validar `botao`. Agora
valida coordenadas inteiras (não bool/float/string), descrição textual e botão
antes de obter backend/consultar geometria; confirma os limites virtuais antes
de `SetCursorPos`. Argumentos locais inválidos devolvem `ToolResult.failure`,
com `mouse_arguments_invalid` ou `mouse_button_invalid`, sem movimento/evento.
O tipo dos argumentos acompanha o contrato existente do Dispatcher; coerções
diretas anteriores, como truncar float ou aceitar bool, deixam de ser aceitas.

Preservados inteiros válidos, origem virtual negativa, botão padrão esquerdo,
aliases nativos `left/right/middle`, normalização textual e sequência de movimento
e eventos. Os aliases não ampliam o enum já existente do Dispatcher. Erros de
limites/execução e sucessos legados mantêm seus retornos anteriores; não houve
migração global de ToolResult ou refatoração de mouse/arraste.

## Seleção UIA

As quatro ferramentas de ação usam inteiro a partir de 1. O wrapper convertia
`indice` com `int` após resolver a janela e retornava texto para zero/negativo.
Uma dessas mensagens não era reconhecida por `from_legacy` e virava sucesso.

O helper compartilhado agora rejeita zero, negativos e tipos não inteiros,
incluindo bool, **antes de resolver janela**, com `ToolResult.failure`, código
`uia_index_invalid` e nome da ferramenta. Não depende de marcadores textuais.
Sucessos e falhas do backend UIA continuam sob o comportamento existente.

Omissão no Python direto continua usando o default **1**; `None` explícito é
inválido. O Dispatcher continua exigindo `indice` explícito com mínimo 1. Não se
alteraram contratos, PermissionManager, preflight, script PowerShell ou seleção
de controles. Faixa superior, empates e controles indisponíveis continuam a
ser validados pelo serviço UIA; não há certificação física desses casos.

## Regressões e limites

`tests/test_native_executor_validation.py` usa somente backends falsos. Distingue
falha estruturada direta, `from_legacy`, sucesso textual compatível, padrão
Python, índices 1/2, erro de faixa devolvido pelo backend falso, tipos inválidos,
ausência no Dispatcher, contratos e negativa/aceitação do PermissionManager.

```powershell
python -m pytest -q tests/test_native_executor_validation.py
```

O relatório externo da etapa 3B.1A registra testes vermelhos/verdes, suíte offline,
SHA local e guardas do ambiente. Não houve API/modelo Live, mouse/teclado real,
janela visível, instalação de VM ou acesso a aplicativos/dispositivos pessoais.
Os demais problemas da auditoria seguem fora do escopo. CI e publicação exigem
nova autorização; testes reais de Windows não estão implicitamente liberados.
