
from types import SimpleNamespace

from core.permission_manager import PermissionManager
from core.tool_contracts import validate_tool_arguments
from tools import dispatcher


def _item(name, arguments):
    return SimpleNamespace(name=name, arguments=arguments)


def test_extra_property_is_rejected_and_tool_not_called(monkeypatch):
    called = []
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, "abrir_programa", lambda *args: called.append(args) or "bad")
    result = dispatcher.executar_ferramenta(
        _item("abrir_programa", '{"programa":"Notepad","extra":1}'),
        PermissionManager(max_actions=10),
        None,
    )
    assert result.ok is False
    assert result.error_code == "contract_error"
    assert called == []


def test_unknown_tool_is_classified_before_contract_lookup():
    result = dispatcher.executar_ferramenta(
        _item("tool_que_nao_existe", '{}'),
        PermissionManager(max_actions=10),
        None,
    )
    assert result.ok is False
    assert result.error_code == "unknown_tool"


def test_all_current_tools_have_handlers_and_contracts():
    from core.tools_registry import tools
    names = {item["name"] for item in tools}
    assert len(names) == 48
    assert names == set(dispatcher.TOOL_HANDLERS)
    assert dispatcher.validar_registry_handlers() == (True, "")
