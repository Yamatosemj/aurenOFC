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


def test_rolar_pagina_espera_por_mudanca_observavel(monkeypatch):
    class _Page:
        def __init__(self):
            self.scroll = 100.0

        def evaluate(self, script):
            script = str(script)
            if "scrollY" in script:
                if "scrollTo" in script:
                    self.scroll = 0.0
                return self.scroll
            return 1000

        def wait_for_function(self, expression, *args, timeout):
            assert timeout == 1500
            if "scrollY >" in expression:
                self.scroll = 900.0
            elif "scrollY <" in expression:
                self.scroll = 0.0
            elif "scrollY === 0" in expression:
                self.scroll = 0.0

        class _Mouse:
            def wheel(self, _x, _y):
                pass

        mouse = _Mouse()

    page = _Page()
    monkeypatch.setattr(browser, "obter_pagina", lambda: page)

    result = browser_navigation.rolar_pagina("baixo")

    assert result.ok is True
    assert result.data["scroll_y_depois"] > result.data["scroll_y_antes"]
