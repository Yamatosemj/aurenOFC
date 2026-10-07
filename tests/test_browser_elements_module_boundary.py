import inspect

import tools.browser as browser
import tools.browser_elements as browser_elements


def test_browser_element_interactions_live_in_dedicated_module():
    public_names = (
        "encontrar_elemento",
        "clicar_elemento",
        "preencher_elemento",
    )

    for name in public_names:
        assert getattr(browser, name) is getattr(browser_elements, name)
        assert getattr(browser, name).__module__ == "tools.browser_elements"


def test_browser_element_module_preserves_nested_element_helpers():
    source = inspect.getsource(browser_elements.encontrar_elemento)
    assert "def visiveis(" in source
    assert "def procurar_atributo(" in source
