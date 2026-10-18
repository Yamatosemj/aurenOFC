# Teste manual da candidata no Windows

Esta candidata reúne as PRs #153 a #160 na branch `integracao/prs-153-160-20261018`. Não inclui Electron/#141 nem histórico de conversas/#142. Main e instalação atual não foram alteradas.

## Preparação

1. Extraia o ZIP da candidata em **pasta nova**. Não extraia por cima do Auren atual.
2. Use Python 3.13 e as dependências de `requirements.txt`. O ZIP é código-fonte; não instala Python, dependências ou browsers.
3. Não copie seu `.env`, bancos, logs ou perfil do Chrome para a candidata. Ela criará seus próprios dados nessa pasta nova. Feche outra instância da mesma candidata antes de reabrir; o banco de tarefas tem dono exclusivo.
4. Confira o SHA/checksum do pacote na PR de integração, junto do resultado final Windows/Linux. Os atalhos podem escolher uma `.venv` da pasta pai; confira o interpretador se tiver ambientes compartilhados.

## Sem API e sem ações pessoais

1. Abra `scripts/iniciar/AUREN_CHROME.bat`. Se necessário, use a URL 127.0.0.1 mostrada no terminal. Não é endereço acessível pela rede.
2. Confira se o orbe e o painel **Tarefas e rotinas** aparecem. **Carregar histórico** deve mostrar a conversa da candidata, sem importar dados do Auren anterior.
3. Cadastre somente um **lembrete local fictício**, por exemplo “conferir exemplo”, com horário próximo e vencimento posterior. Ele deve aparecer como rascunho; salvar não autoriza execução.
4. Se quiser testar o aviso local, autorize esse lembrete separadamente, mantendo a conversa selecionada e o aplicativo aberto. Ele não usa IA. Confira que aparece uma vez; ou revogue antes do horário e confira que não aparece.
5. Feche o servidor com Ctrl+C; fechar só a aba não encerra o servidor. Reabra a candidata, carregue o histórico e selecione a conversa: a rotina deve manter seu estado, sem reautorizar/repetir automaticamente.
6. Para conferir também a GUI antiga, feche o servidor anterior e abra `scripts/iniciar/ABRIR_AUREN_GUI.bat`. Verifique a tabela de tarefas e o fechamento. Tk não possui o formulário de rotinas do Chrome.

O envio de mensagens normais pode chamar a API e executar ferramentas. Não é parte desse roteiro gratuito. Não reaproveitamos autorização de outro lote para iniciar testes pagos ou com arquivos/aplicativos pessoais.

## Bateria integrada automática gratuita

Na pasta da candidata, com pytest e dependências disponíveis:

```powershell
py -3.13 -m pytest tests/test_integration_consolidated.py -q
```

São quatro casos que criam fontes/perfil/arquivos temporários, retiram credenciais e simulam somente as respostas do SDK: planejamento e pausa/retomada pelo HTTP, confirmação negada, lembrete persistente e banco corrompido. Não usam API ou dados pessoais e encerram os seus próprios servidores/processos. Não alteram a main nem a instalação existente.

## Avaliação com IA real, quando autorizada separadamente

Com cenários e orçamento definidos, use somente dois TXT fictícios em uma pasta permitida e peça para ler códigos e somar números. Confira cada etapa, pause, feche, reabra, selecione a conversa e retome. A primeira leitura não deve se repetir; o mesmo objetivo deve continuar. Ações sensíveis devem continuar pedindo sua confirmação. Não autorize uma ação se o alvo/valor mostrado não corresponder ao pedido.

Registre o objetivo fictício, resultado observado, horário e estado mostrado. Não publique chave ou conteúdo pessoal em capturas. Limitações e evidências estão em [RELATORIO_INTEGRACAO.md](RELATORIO_INTEGRACAO.md).
