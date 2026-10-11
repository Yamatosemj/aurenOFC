# Scripts auxiliares do Auren

Abra **`iniciar/ABRIR_AUREN_GUI.bat`** para usar o Auren com interface grafica.
Os demais atalhos sao opcionais e estao agrupados por funcao:

- **iniciar/** — interface desktop ou voz
- **instalar/** — dependencias Python e de voz
- **testar/** — baterias de regressao
- **diagnosticos/** — microfones, metricas, custo e ferramentas de analise
- **experimentos/** — capacidades experimentais desativadas por padrao

Todos os arquivos `.bat` ajustam o diretorio para a raiz do projeto, independentemente da pasta de onde forem abertos.

**Importante:** instalar e iniciar não escolhem necessariamente o mesmo interpretador Python: o atalho da GUI usa o global, o de voz procura `.venv`, e `TESTAR_AUREN.bat` sem argumentos inclui L4 com modelo/API e possíveis efeitos. Consulte [Etapa 10 — Entradas e instalação](../docs/architecture/10-entradas-config-instalacao-distribuicao.md) antes de executar ou diagnosticar esses atalhos. Os scripts Python do programa e os pontos de entrada legados permanecem na raiz quando existe risco de quebrar imports ou automacoes.
