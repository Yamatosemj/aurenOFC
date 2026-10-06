# Auren

Assistente desktop/voz para Windows, versão técnica **V46**, usando o modelo configurado em `config.py` (snapshot atual: `gpt-5.6-luna`).

## Estrutura

```text
agent/       orquestração e componentes Ari adaptados
brains/      Fast/Deep
core/        contratos, roteamento, Harness, memória, visão e permissões
memory/      persistência SQLite
providers/   provider do modelo
skills/      carregamento de skills
tools/       capacidades executáveis
voice/       STT/TTS/entrada de voz
tests/       suíte pytest
```

## Executar

```powershell
python main.py
```

ou

```powershell
python auren.py
```

Para voz:

```powershell
AUREN_VOZ.bat
```

## Instalação

```powershell
INSTALAR_AUREN.bat
INSTALAR_VOZ.bat
```

A camada de voz usa dependências separadas de `requirements-voice.txt`.

## Testes

```powershell
py -m pytest -q
python testes_auren.py --rapido
python testes_auren.py --completo
```

Última validação do snapshot V46 corrigido: **137/137 testes pytest passando**.

Os resultados gerados por `testes_auren.py` ficam em:

```text
logs/testes/RESULTADO_TESTE_AUREN.txt
```

## Arquitetura atual

```text
Entrada
  -> Harness
  -> Orchestrator
  -> LLMRouter / Router
  -> Brain
  -> OpenAIProvider
```

As ferramentas passam pelo Dispatcher, contratos e permissões antes da execução.

## Estado importante

- **45 tools** no registry/contratos atuais
- memória persistente em SQLite
- browser e automação Windows integrados
- voice local-first para ASR/TTS
- `wake_word.py` existe, mas não faz parte do caminho normal de voz atual (PTT/F8)
- componentes históricos e relatórios antigos não fazem parte deste pacote runtime

## Licença

Os componentes derivados/adaptados do Ari-VoiceCommand estão cobertos por `LICENSE_ARIVC_MIT.txt`.

## Histórico

A documentação de versões anteriores foi retirada do pacote principal para manter a raiz limpa. Ela deve ser mantida separadamente, fora do runtime.
