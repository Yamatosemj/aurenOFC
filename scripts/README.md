# Scripts auxiliares do Auren

Abra **`iniciar/ABRIR_AUREN_GUI.bat`** para usar o Auren com interface grafica.
Os demais atalhos sao opcionais e estao agrupados por funcao:

- **iniciar/** — interface desktop ou voz
- **instalar/** — dependencias Python e de voz
- **testar/** — baterias de regressao
- **diagnosticos/** — microfones, metricas, custo e ferramentas de analise
- **experimentos/** — capacidades experimentais desativadas por padrao

Todos os arquivos `.bat` ajustam o diretorio para a raiz do projeto, independentemente da pasta de onde forem abertos.

**Atalhos principais:** instalação, GUI/Chrome, voz e testes usam `lib/SELECIONAR_PYTHON.cmd`, nesta ordem: `.venv` do projeto, `..\\.venv` da pasta pai, `py -3` ou `python`. O helper informa o Python escolhido e falha com mensagem se nenhum for encontrado; não cria ambientes automaticamente. Se o ambiente da pasta pai pertencer a outro projeto, é recomendável criar uma `.venv` própria antes de instalar. `TESTAR_AUREN.bat` sem argumentos continua **somente L0,L1**; L2/L4/L5 exigem seleção explícita e podem alterar o PC/usar API. Diagnósticos/experimentos possuem seus próprios contratos e não foram padronizados nesta correção. Veja a [Etapa 10](../docs/architecture/10-entradas-config-instalacao-distribuicao.md).
