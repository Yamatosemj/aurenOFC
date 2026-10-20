"""Selection contracts and executor safety; no desktop or network access."""
import json
import re
from types import SimpleNamespace

import pytest

from core.permission_manager import PermissionManager
from core.tool_contracts import validate_tool_arguments
from core.tool_result import ToolResult, from_legacy
from tools import browser, browser_elements, dispatcher


class Element:
    def __init__(self, accessible_name="Alvo", role="button", **attrs):
        self.name, self.role, self.attrs = accessible_name, role, attrs
        self.clicks, self.value = 0, ""

    def is_visible(self):
        return not self.attrs.get("hidden", False)

    def evaluate(self, script):
        return "input" if self.role == "textbox" else "button"

    def get_attribute(self, name):
        return self.attrs.get(name)

    def click(self, timeout):
        self.clicks += 1

    def fill(self, text, timeout):
        self.value = text


class Locator:
    def __init__(self, elements):
        self.elements = elements

    def count(self):
        return len(self.elements)

    def nth(self, index):
        return self.elements[index]


class Page:
    url = "about:blank"

    def __init__(self, elements):
        self.elements = elements

    def get_by_role(self, role, name):
        return Locator([e for e in self.elements if e.role == role and name.search(e.name)])

    def get_by_label(self, name):
        return Locator([e for e in self.elements if name.search(e.attrs.get("aria-label", ""))])

    def get_by_placeholder(self, name):
        return Locator([e for e in self.elements if name.search(e.attrs.get("placeholder", ""))])

    def get_by_text(self, name):
        return Locator([e for e in self.elements if name.search(e.name)])

    def locator(self, selector):
        attr, value = re.search(r'\[([^=]+)=(".*?")\]', selector).groups()
        value = json.loads(value)
        return Locator([e for e in self.elements if e.attrs.get(attr) == value])

    def wait_for_timeout(self, ms):
        pass


@pytest.fixture
def page(monkeypatch):
    p = Page([])
    monkeypatch.setattr(browser, "obter_pagina", lambda: p)
    monkeypatch.setattr(browser, "_paginas_abertas", lambda: [p])
    return p


def execute(tool, args):
    return getattr(browser_elements, tool)(**args)


def arguments(tool, **changes):
    args = {"alvo": "Alvo", "indice": 1}
    if tool == "preencher_elemento":
        args["texto"] = "fixture"
    args.update(changes)
    return args


TOOLS = ("clicar_elemento", "preencher_elemento")


@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize("index", [0, -1, 3, None, True, "1", 1.5])
def test_invalid_selection_is_structured_and_has_no_effect(page, tool, index):
    page.elements = [Element(role="textbox" if tool.startswith("preencher") else "button")]
    result = execute(tool, arguments(tool, indice=index))
    assert isinstance(result, ToolResult)
    assert not result.ok
    assert result.error_code == "invalid_selection"
    assert [(e.clicks, e.value) for e in page.elements] == [(0, "")]


@pytest.mark.parametrize("tool", TOOLS)
def test_missing_index_does_not_choose_first_duplicate(page, tool):
    role = "textbox" if tool.startswith("preencher") else "button"
    page.elements = [Element(role=role), Element(role=role)]
    args = arguments(tool)
    del args["indice"]
    result = execute(tool, args)
    assert isinstance(result, ToolResult) and not result.ok
    assert result.error_code == "invalid_selection"
    assert [(e.clicks, e.value) for e in page.elements] == [(0, ""), (0, "")]


@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize("index", [1, 2])
def test_explicit_duplicate_index_is_preserved(page, tool, index):
    role = "textbox" if tool.startswith("preencher") else "button"
    page.elements = [Element(role=role), Element(role=role)]
    result = from_legacy(execute(tool, arguments(tool, indice=index)))
    assert result.ok
    expected = [(0, ""), (0, "")]
    expected[index - 1] = (0, "fixture") if role == "textbox" else (1, "")
    assert [(e.clicks, e.value) for e in page.elements] == expected


@pytest.mark.parametrize("tool", TOOLS)
def test_out_of_range_exact_match_never_falls_back_to_partial(page, tool):
    role = "textbox" if tool.startswith("preencher") else "button"
    page.elements = [Element(role=role), Element("Alvo extra", role)]
    result = from_legacy(execute(tool, arguments(tool, indice=2)))
    assert not result.ok
    assert result.error_code == "invalid_selection"
    assert [(e.clicks, e.value) for e in page.elements] == [(0, ""), (0, "")]


@pytest.mark.parametrize("tool,missing", [(t, k) for t in TOOLS for k in arguments(t)])
def test_missing_required_arguments_are_rejected_before_permission(monkeypatch, tool, missing):
    args = arguments(tool)
    del args[missing]
    pm = PermissionManager()
    monkeypatch.setattr(pm, "autorizar", lambda *a: pytest.fail("permission must not be requested"))
    result = dispatcher.executar_ferramenta(SimpleNamespace(name=tool, arguments=json.dumps(args)), pm, None)
    assert not result.ok and result.error_code == "contract_error"


@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize("index", [0, -1, None, True, "1", 1.5])
def test_invalid_index_contract_precedes_permission(monkeypatch, tool, index):
    pm = PermissionManager()
    monkeypatch.setattr(pm, "autorizar", lambda *a: pytest.fail("permission must not be requested"))
    result = dispatcher.executar_ferramenta(
        SimpleNamespace(name=tool, arguments=json.dumps(arguments(tool, indice=index))), pm, None)
    assert not result.ok and result.error_code == "contract_error"


@pytest.mark.parametrize("target", ["", "   ", None, 42])
@pytest.mark.parametrize("tool", TOOLS)
def test_invalid_target_cannot_act(page, tool, target):
    page.elements = [Element()]
    result = execute(tool, arguments(tool, alvo=target))
    assert isinstance(result, ToolResult) and not result.ok
    assert result.error_code == "invalid_selection"
    assert page.elements[0].clicks == 0 and page.elements[0].value == ""


def test_zero_keeps_its_active_tab_meaning():
    assert validate_tool_arguments("fechar_aba", {"indice": 0}) == (True, "")


@pytest.mark.parametrize("tool", TOOLS)
def test_missing_index_does_not_even_obtain_page(monkeypatch, tool):
    monkeypatch.setattr(browser, "obter_pagina", lambda: pytest.fail("no page should be opened"))
    result = execute(tool, {k: v for k, v in arguments(tool).items() if k != "indice"})
    assert isinstance(result, ToolResult) and result.error_code == "invalid_selection"


@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize("name,target", [("Alvo", "Alvo"), ("Alvo extra", "Alvo"), ("A[1]", "A[1]")])
def test_unique_exact_and_partial_matches_still_work(page, tool, name, target):
    role = "textbox" if tool.startswith("preencher") else "button"
    page.elements = [Element(name, role)]
    result = from_legacy(execute(tool, arguments(tool, alvo=target)))
    assert result.ok
    assert (page.elements[0].clicks, page.elements[0].value) == (
        (0, "fixture") if role == "textbox" else (1, ""))


@pytest.mark.parametrize("attr", ["id", "name", "aria-label", "placeholder"])
def test_attribute_range_error_does_not_fall_through(page, attr):
    page.elements = [Element("Outro", "textbox", **{attr: "Alvo"}),
                     Element("Alvo", "textbox"), Element("Alvo", "textbox")]
    result = from_legacy(browser_elements.preencher_elemento("Alvo", "fixture", 2))
    assert not result.ok and result.error_code == "invalid_selection"
    assert all(e.value == "" for e in page.elements)


@pytest.mark.parametrize("tool", TOOLS)
def test_hidden_elements_are_not_counted(page, tool):
    role = "textbox" if tool.startswith("preencher") else "button"
    page.elements = [Element(role=role, hidden=True), Element(role=role)]
    result = from_legacy(execute(tool, arguments(tool)))
    assert result.ok
    assert (page.elements[0].clicks, page.elements[0].value) == (0, "")
    assert (page.elements[1].clicks, page.elements[1].value) != (0, "")


@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize("approved", [True, False])
def test_dispatcher_preserves_real_permission_decision(page, tool, approved):
    page.elements = [Element(role="textbox" if tool.startswith("preencher") else "button")]
    requests = []
    channel = SimpleNamespace(confirmar=lambda req: requests.append(req) or approved)
    pm = PermissionManager(confirmation_channel=channel)
    result = dispatcher.executar_ferramenta(
        SimpleNamespace(name=tool, arguments=json.dumps(arguments(tool))), pm, None)
    assert len(requests) == 1
    assert result.ok is approved
    if not approved:
        assert result.error_code == "permission_denied"
        assert (page.elements[0].clicks, page.elements[0].value) == (0, "")


def test_zero_closes_active_tab_not_first(monkeypatch):
    tabs = [SimpleNamespace(closed=False), SimpleNamespace(closed=False)]
    for tab in tabs:
        tab.close = lambda tab=tab: setattr(tab, "closed", True)
    monkeypatch.setattr(browser, "pagina", tabs[1])
    monkeypatch.setattr(browser, "_paginas_abertas", lambda: [t for t in tabs if not t.closed])
    monkeypatch.setattr(browser, "_estado_abas", lambda: "fixture")
    assert from_legacy(browser.fechar_aba(0)).ok
    assert [t.closed for t in tabs] == [False, True]


@pytest.mark.parametrize("tool", TOOLS)
def test_unknown_target_fails_without_side_effect(page, tool):
    page.elements = [Element("Diferente", "textbox" if tool.startswith("preencher") else "button")]
    result = from_legacy(execute(tool, arguments(tool)))
    assert not result.ok and result.error_code == "invalid_selection"
    assert (page.elements[0].clicks, page.elements[0].value) == (0, "")


@pytest.mark.parametrize("tool", TOOLS)
def test_range_error_never_changes_role(page, tool):
    roles = ("searchbox", "textbox") if tool.startswith("preencher") else ("button", "link")
    page.elements = [Element(role=roles[0]), Element(role=roles[1]), Element(role=roles[1])]
    result = from_legacy(execute(tool, arguments(tool, indice=2)))
    assert not result.ok and result.error_code == "invalid_selection"
    assert all((e.clicks, e.value) == (0, "") for e in page.elements)


@pytest.mark.parametrize("method", ["get_by_label", "get_by_placeholder", "get_by_text"])
@pytest.mark.parametrize("index", [1, 2, 3])
@pytest.mark.parametrize("tool", TOOLS)
def test_last_resort_match_obeys_explicit_range(page, monkeypatch, method, index, tool):
    page.elements = [Element(role="generic"), Element(role="generic")]
    monkeypatch.setattr(page, "get_by_role", lambda *a, **kw: Locator([]))
    monkeypatch.setattr(page, "locator", lambda *a: Locator([]))
    for name in ("get_by_label", "get_by_placeholder", "get_by_text"):
        monkeypatch.setattr(page, name, lambda *a: Locator([]))
    monkeypatch.setattr(page, method, lambda *a: Locator(page.elements))
    result = from_legacy(execute(tool, arguments(tool, indice=index)))
    assert result.ok is (index < 3)
    if index == 3:
        assert result.error_code == "invalid_selection"
        assert all((e.clicks, e.value) == (0, "") for e in page.elements)
    else:
        assert (page.elements[index - 1].clicks, page.elements[index - 1].value) == (
            (0, "fixture") if tool.startswith("preencher") else (1, ""))
