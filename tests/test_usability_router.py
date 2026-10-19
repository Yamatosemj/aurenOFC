import pytest
from core.router import Router
from core.tools_registry import tools

@pytest.mark.parametrize('text', ['Olá!', 'oi auren', 'bom dia', 'Explique o que é uma metáfora.'])
def test_self_contained_conversation_does_not_load_tools(text):
    assert Router().select_tools(text, tools) == []

@pytest.mark.parametrize('text', ['faça isso', 'continue', 'Olá, abra o aplicativo',
    'Explique o que é uma metáfora e abra Calculadora', 'Explique o que é uma janela',
    'Leia arquivo.txt', 'Qual o volume atual do Windows?'])
def test_action_and_continuation_keep_capabilities(text):
    assert Router().select_tools(text, tools)

def test_next_request_can_expand_from_greeting_to_any_capability():
    router = Router()
    assert router.select_tools('oi', tools) == []
    assert router.select_tools('faça isso', tools) == tools
    assert any(t['name'] == 'abrir_programa' for t in router.select_tools('abra o aplicativo de teste', tools))
