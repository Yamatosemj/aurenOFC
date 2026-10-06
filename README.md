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

Última validação completa registrada do snapshot V46: **216/216 testes pytest passando**. As alterações de limpeza posteriores são pequenas e não foram revalidadas nesta sessão.

Os resultados gerados por `testes_auren.py` ficam em:

```text
logs/testes/RESULTADO_TESTE_AUREN.txt
```

## Inteligência de Arquivos (V46)

A capacidade de arquivos mantém `buscar_arquivo` como busca existente e adiciona duas tools pelo mesmo Dispatcher, contratos e permissões:

- `inspecionar_arquivo`: metadados, tipo detectado, tamanho, datas, SHA-256, estado e evidências locais de origem. Pode procurar cópias confirmadas por hash.
- `ler_arquivo`: leitura controlada de `.txt`, `.md`, `.json` e `.csv`, com encoding detectado e continuação por trechos.

Origem e histórico são tratados como evidência: Zone.Identifier/URL só são reportados quando acessíveis; relação entre cópias é confirmada por SHA-256; trajetória completa permanece desconhecida. PDF pode ser identificado por assinatura, mas leitura de conteúdo ainda não está implementada. DOCX, XLSX e OCR continuam fora do escopo desta etapa.

## Arquitetura atual

```text
Entrada
  -> Harness
  -> Orchestrator
  -> Router
  -> Brain
  -> OpenAIProvider

                 -> function_call
Modelo
                 -> Dispatcher
                 -> Contrato
                 -> Permissao
                 -> Ferramenta
                 -> ToolResult
                 -> Harness
```

O Router escolhe o conjunto de ferramentas da rodada. Toda execução de ferramenta passa pelo Dispatcher, validação de contrato e permissões antes de chegar ao executor. O resultado estruturado volta ao Harness como `ToolResult`.

## Estado importante

- **47 tools** no registry/contratos atuais
- memória persistente em SQLite
- browser e automação Windows integrados
- voice local-first para ASR/TTS
- `wake_word.py` existe, mas não faz parte do caminho normal de voz atual (PTT/F8)
- componentes históricos e relatórios antigos não fazem parte deste pacote runtime

## Licença

Os componentes derivados/adaptados do Ari-VoiceCommand estão cobertos por `LICENSE_ARIVC_MIT.txt`.

## Histórico

A documentação de versões anteriores foi retirada do pacote principal para manter a raiz limpa. Ela deve ser mantida separadamente, fora do runtime.
