"""Regressions for binding a file decision to the path actually accessed."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import core.permission_manager as permission_module
from core.permission_manager import PermissionManager
import tools.dispatcher as dispatcher
import tools.file_intelligence as file_intelligence


class ConfirmationChannel:
    def __init__(self, approved=True):
        self.approved = approved
        self.requests = []

    def confirmar(self, request):
        self.requests.append(request)
        return self.approved


def _execute(tool, path, manager):
    arguments = {"caminho": str(path)}
    if tool == "ler_arquivo":
        arguments.update(inicio=0, limite_caracteres=100)
    else:
        arguments.update(procurar_copias=False, limite_copias=5)
    return dispatcher.executar_ferramenta(
        SimpleNamespace(name=tool, arguments=json.dumps(arguments)), manager, None
    )


@pytest.fixture
def paths(tmp_path, monkeypatch):
    allowed = tmp_path / "Desktop"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    first = allowed / "first.txt"
    other = outside / "other.txt"
    third = outside / "third.txt"
    sensitive = allowed / ".ssh" / "secret.txt"
    sensitive.parent.mkdir()
    for path, content in (
        (first, "FIRST_SYNTHETIC"),
        (other, "OTHER_SYNTHETIC"),
        (third, "THIRD_SYNTHETIC"),
        (sensitive, "SENSITIVE_SYNTHETIC"),
    ):
        path.write_text(content, encoding="utf-8")
    monkeypatch.setattr(file_intelligence, "_read_allowed_roots", lambda: [allowed.resolve()])
    return first, other, third, sensitive, tmp_path / "alias.txt"


def _switching_alias(monkeypatch, alias, initial):
    """Simulate a link whose resolved target changes after authorization."""
    current = {"target": initial}
    original = file_intelligence._resolve_path

    def resolve(value):
        return current["target"] if str(value) == str(alias) else original(value)

    monkeypatch.setattr(file_intelligence, "_resolve_path", resolve)
    monkeypatch.setattr(permission_module, "_resolve_path", resolve)
    return current


@pytest.mark.parametrize("tool", ["ler_arquivo", "inspecionar_arquivo"])
def test_allowed_destination_changed_to_external_is_rejected(paths, monkeypatch, tool):
    first, other, _, _, alias = paths
    current = _switching_alias(monkeypatch, alias, first)
    channel = ConfirmationChannel()
    manager = PermissionManager(confirmation_channel=channel)
    authorize = manager.autorizar

    def switch_after_authorization(name, arguments):
        decision = authorize(name, arguments)
        current["target"] = other
        return decision

    monkeypatch.setattr(manager, "autorizar", switch_after_authorization)
    result = _execute(tool, alias, manager)
    assert result.ok is False
    assert result.error_code == "file_path_changed"
    assert channel.requests == []


@pytest.mark.parametrize("tool", ["ler_arquivo", "inspecionar_arquivo"])
def test_confirmed_external_destination_changed_to_another_is_rejected(paths, monkeypatch, tool):
    _, other, third, _, alias = paths
    current = _switching_alias(monkeypatch, alias, third)
    channel = ConfirmationChannel()
    manager = PermissionManager(confirmation_channel=channel)
    authorize = manager.autorizar

    def switch_after_authorization(name, arguments):
        decision = authorize(name, arguments)
        current["target"] = other
        return decision

    monkeypatch.setattr(manager, "autorizar", switch_after_authorization)
    result = _execute(tool, alias, manager)
    assert result.ok is False
    assert result.error_code == "file_path_changed"
    assert len(channel.requests) == 1
    assert repr(str(third)) in channel.requests[0].action


@pytest.mark.parametrize("tool", ["ler_arquivo", "inspecionar_arquivo"])
def test_destination_changed_after_dispatcher_check_is_rejected_by_handler(paths, monkeypatch, tool):
    first, other, _, _, alias = paths
    current = _switching_alias(monkeypatch, alias, first)
    handler = dispatcher.TOOL_HANDLERS[tool]

    def switch_before_handler(arguments, memory_store, context):
        current["target"] = other
        return handler(arguments, memory_store, context)

    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, tool, switch_before_handler)
    result = _execute(tool, alias, PermissionManager(confirmation_channel=ConfirmationChannel()))
    assert result.ok is False
    assert result.error_code == "file_path_changed"


@pytest.mark.parametrize("tool", ["ler_arquivo", "inspecionar_arquivo"])
def test_confirmation_displays_canonical_destination_and_legitimate_access_works(paths, monkeypatch, tool):
    _, _, third, _, alias = paths
    _switching_alias(monkeypatch, alias, third)
    channel = ConfirmationChannel()
    result = _execute(tool, alias, PermissionManager(confirmation_channel=channel))
    assert result.ok is True
    assert len(channel.requests) == 1
    assert repr(str(third)) in channel.requests[0].action
    assert repr(str(alias)) not in channel.requests[0].action
    if tool == "ler_arquivo":
        assert result.data["file_content"]["conteudo"] == "THIRD_SYNTHETIC"
    else:
        assert result.data["file_info"]["caminho"] == str(third)


@pytest.mark.parametrize("tool", ["ler_arquivo", "inspecionar_arquivo"])
def test_allowed_destination_without_change_stays_automatic(paths, monkeypatch, tool):
    first, _, _, _, alias = paths
    _switching_alias(monkeypatch, alias, first)
    channel = ConfirmationChannel()
    result = _execute(tool, alias, PermissionManager(confirmation_channel=channel))
    assert result.ok is True
    assert channel.requests == []
    if tool == "ler_arquivo":
        assert result.data["file_content"]["conteudo"] == "FIRST_SYNTHETIC"
    else:
        assert result.data["file_info"]["caminho"] == str(first)


@pytest.mark.parametrize("tool", ["ler_arquivo", "inspecionar_arquivo"])
def test_denied_and_sensitive_paths_remain_blocked(paths, monkeypatch, tool):
    _, other, _, sensitive, alias = paths
    _switching_alias(monkeypatch, alias, other)
    channel = ConfirmationChannel(approved=False)
    denied = _execute(tool, alias, PermissionManager(confirmation_channel=channel))
    assert denied.ok is False
    assert denied.error_code == "permission_denied"
    assert len(channel.requests) == 1

    channel = ConfirmationChannel()
    blocked = _execute(tool, sensitive, PermissionManager(confirmation_channel=channel))
    assert blocked.ok is False
    assert blocked.error_code == "permission_denied"
    assert channel.requests == []
