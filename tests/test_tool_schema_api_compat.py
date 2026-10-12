"""Protecao offline contra o erro 400 de schema no catalogo de ferramentas.

Em 12/10/2026, uma saudacao falhou antes de o modelo responder porque
clicar_mouse_windows usava strict=True com propriedades opcionais fora de
required. Nao se faz chamada real a API nem ao Windows nestes testes.
"""
from __future__ import annotations

from types import SimpleNamespace

from core.tool_contracts import validate_tool_arguments
from core.tools_registry import tools
from providers.openai_provider import OpenAIProvider


OPTIONAL_COORDINATE_TOOLS = {"clicar_mouse_windows", "arrastar_mouse_windows"}


def test_registry_todo_valido_para_modo_strict_da_responses_api():
    assert len(tools) == 49
    assert len({tool["name"] for tool in tools}) == len(tools)

    non_strict = set()
    for tool in tools:
        schema = tool["parameters"]
        propriedades = set(schema.get("properties") or {})
        obrigatorias = schema.get("required")
        assert schema.get("type") == "object", tool["name"]
        assert isinstance(obrigatorias, list), tool["name"]
        assert len(obrigatorias) == len(set(obrigatorias)), tool["name"]
        assert set(obrigatorias) <= propriedades, tool["name"]
        assert schema.get("additionalProperties") is False, tool["name"]

        if tool["strict"]:
            # A Responses API rejeita strict=True quando 'required' nao
            # contem TODAS as propriedades, inclusive as opcionais.
            assert set(obrigatorias) == propriedades, tool["name"]
        else:
            non_strict.add(tool["name"])
            assert propriedades - set(obrigatorias) == {
                "coordinate_space", "vision_snapshot_id"
            }, tool["name"]
    assert non_strict == OPTIONAL_COORDINATE_TOOLS


def test_campos_visuais_opcionais_continuam_opcionais_no_dispatcher():
    exemplos = {
        "clicar_mouse_windows": {
            "x": 200, "y": 100, "botao": "esquerdo", "descricao": "botao visivel",
        },
        "arrastar_mouse_windows": {
            "x_inicial": 100, "y_inicial": 100,
            "x_final": 200, "y_final": 200,
            "botao": "esquerdo", "duracao_ms": 300, "descricao": "mover item",
        },
    }
    for nome, argumentos in exemplos.items():
        ok, erro = validate_tool_arguments(nome, argumentos)
        assert ok, (nome, erro)

        # O modo nao estrito na API NAO desabilita os contratos locais.
        invalidos = dict(argumentos, coordinate_space="nao_existe")
        ok, _erro = validate_tool_arguments(nome, invalidos)
        assert not ok

        invalidos = dict(argumentos, extra="nao_autorizado")
        ok, _erro = validate_tool_arguments(nome, invalidos)
        assert not ok


def test_provider_envia_catalogo_compativel_em_saudacao_sem_chamar_api(monkeypatch):
    enviados = []

    def fake_create(**kwargs):
        enviados.append(kwargs)
        return SimpleNamespace(output=[], output_text="Ola!")

    provider = OpenAIProvider()
    monkeypatch.setattr(
        provider, "get_client",
        lambda: SimpleNamespace(responses=SimpleNamespace(create=fake_create)),
    )
    monkeypatch.setattr("providers.openai_provider.usage.registrar_uso", lambda _resp: None)

    resposta = provider.create_response("ola auren", tools=None)
    assert resposta.output_text == "Ola!"
    assert len(enviados) == 1
    chamadas = enviados[0]
    assert len(chamadas["tools"]) == 49
    assert {tool["name"] for tool in chamadas["tools"] if not tool["strict"]} == OPTIONAL_COORDINATE_TOOLS
    for tool in chamadas["tools"]:
        if tool["strict"]:
            props = set(tool["parameters"]["properties"])
            required = set(tool["parameters"]["required"])
            assert required == props, tool["name"]
