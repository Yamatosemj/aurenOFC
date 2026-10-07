import tools.browser as browser
import tools.browser_navigation as browser_navigation


def test_browser_navigation_controls_live_in_dedicated_module():
    public_names = (
        "pressionar_tecla",
        "voltar_pagina",
        "avancar_pagina",
        "recarregar_pagina",
        "rolar_pagina",
    )

    for name in public_names:
        assert getattr(browser, name) is getattr(browser_navigation, name)
        assert getattr(browser, name).__module__ == "tools.browser_navigation"
