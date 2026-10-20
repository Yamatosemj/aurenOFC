# Experimento opt-in — roteamento local + descoberta dinamica (19/10/2026)

## Objetivo

Combinar dois padroes conhecidos sem copiar suas implementacoes:
- Home Assistant Assist: frases reconhecidas com alta certeza sao tratadas localmente;
- OpenClaw Tool Search: um catalogo grande nao precisa expor todos os schemas no primeiro contato.

O Auren ja tinha local decision, Router, Dispatcher, ToolContractRegistry e PermissionManager.
Este experimento reutiliza esses componentes em vez de criar outro executor ou outro modelo.

## Como habilitar (somente em uma instalacao de teste)

Definir `AUREN_DYNAMIC_TOOL_DISCOVERY=1` **antes** de iniciar o processo Python.
Reiniciar o Auren ao mudar a flag. Sem a variavel, todo o comportamento antigo
de tool routing e dos atalhos locais permanece igual.

Nao habilitar na instalacao pessoal. A autorizacao especifica de API paga da
PR #173 foi exercida somente com handlers sinteticos: houve regressoes reais
de selecao, sem acoes no desktop. [Relatorio, custos e limites](PR173_VALIDACAO.md).

## Comportamento do prototipo

1. Intents deterministicas existentes: status, URL, sites e abas continuam locais.
2. Com opt-in, proxima musica/musica anterior/parar musica e volume/mudo, quando expressos na gramatica
   exata de `LocalDecisionEngine`, tambem sao encaminhados ao mesmo Dispatcher
   pelo mesmo `fast_paths`. Frases compostas nao ganham atalhos novos.
3. As conversas explicitas identificadas pelo Router continuam sem schemas.
4. Dominios reconhecidos mantem as ferramentas especializadas atuais.
5. Se nao houver dominio claro, a rodada recebe **apenas** `buscar_ferramentas`
   em vez de 49 schemas.
6. `buscar_ferramentas` procura deterministicamente nos nomes/descricoes locais
   e devolve no maximo cinco nomes e descricoes compactas. Ela NAO executa.
7. Na proxima rodada, quando um `function_call_output` corresponde a um
   `function_call` genuino de busca (mesmo `call_id`), o Router expõe
   os schemas que vieram da busca, a uniao dos dominios do objetivo e a busca.
   Metadados sao recalculados dos argumentos registrados; IDs duplicados,
   outputs fora de ordem e payloads divergentes sao rejeitados. A ferramenta
   da rodada anterior permanece disponivel sem cache entre tarefas.
8. Chamadas executaveis continuam pelo **Dispatcher, contrato, PermissionManager,
   guards de tarefa e verificacao de resultado**. Nenhuma autorizacao e
   passada junto dos metadados de busca.

## Limites conhecidos e riscos

- Busca local e lexical, nao semantica; pode omitir a ferramenta certa.
- A consulta escolhida pelo modelo pode inventar o dominio errado; o Live
  reproduziu isso mesmo quando o schema correto estava entre os candidatos.
- "proximo", "anterior", "pausa" e "play" nao ganham executor local no modo
  experimental: podem ser referencias ambiguas ou um toggle sem estado conhecido.
- Um pedido desconhecido que precisa de acao exige uma rodada de busca adicional.
  Portanto reduzir tokens iniciais **pode piorar a latencia**: medir.
- O input das continuacoes guarda a rodada imediatamente anterior, nao uma
  memoria permanente de todas as ferramentas descobertas. Tarefas de varias
  etapas podem precisar pesquisar novamente.
- Nao introduz um `dispatch_action` universal. Os schemas reais sao carregados
  na rodada seguinte; nao ha caminho paralelo ao Dispatcher.
- O prototipo nao substitui a classificacao do modelo em pedidos ambiguos.
- Os comandos de audio selecionados localmente nao contornam permissao,
  verificacao previa do Harness nem confirmacoes. Sao apenas reversiveis.
- Nenhum sucesso em UI/Windows/voz/browser, custo real ou melhora de latencia
  e inferido dos testes offline.
- Nenhuma instalacao pessoal, branch principal ou PR anterior deve ser alterada
  automaticamente por este experimento.

## Testes e criterios de aceite

Teste offline: `python -m pytest -q tests/test_dynamic_tool_discovery.py`.
O teste usa subprocessos separados para verificar o modo legado sem flag e o
modo opt-in com flag, sem rede, sem SDK Live e sem executar ferramentas reais.

Antes de qualquer rollout:
1. CI completo na branch final, inclusive Windows e Linux.
2. Pedidos negativos: conversa natural, referencia ambigua, texto de pagina,
   multiplos dominios, chamada sem `call_id`, ferramenta inexistente.
3. Pedidos positivos: comandos locais, descobertas e execucoes reais autorizadas.
4. Comparar `tool_schema_chars`, `input_tokens`, `cached_tokens`,
   `output_tokens`, quantidade de rodadas, tempo ate a primeira resposta,
   tempo ate conclusao e taxa de sucesso por tarefa.
5. Medir pelo menos 100 pedidos variados versus a versao base; nao concluir
   que o metodo e mais barato so pela reducao de schemas na primeira rodada.

## Fontes de conceito

- Home Assistant: https://www.home-assistant.io/integrations/conversation/
- OpenClaw: https://github.com/openclaw/openclaw/blob/main/docs/tools/tool-search.md
