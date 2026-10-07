import tools.browser as browser
import tools.browser_reading as browser_reading


def test_browser_page_reader_lives_in_dedicated_module():
    assert browser.ler_pagina is browser_reading.ler_pagina
    assert browser.ler_pagina.__module__ == "tools.browser_reading"


def test_browser_page_reader_module_owns_read_implementation():
    assert hasattr(browser_reading, "ler_pagina")
