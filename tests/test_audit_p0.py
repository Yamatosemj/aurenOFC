"""AUD-001: somente arquivos ficticios; nenhuma confirmacao interativa."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import core.permission_manager as permissions
from core.permission_manager import PermissionManager
from tools import dispatcher, file_intelligence as files


class Decision:
    def __init__(self, callback=None, approved=True):
        self.callback = callback
        self.approved = approved
        self.requests = []

    def confirmar(self, request):
        self.requests.append(request)
        if self.callback:
            self.callback()
        return self.approved


def execute(path, channel, tool):
    args = ({"caminho": str(path), "inicio": 0, "limite_caracteres": 100}
            if tool == "ler_arquivo" else
            {"caminho": str(path), "procurar_copias": False, "limite_copias": 5})
    return dispatcher.executar_ferramenta(
        SimpleNamespace(name=tool, arguments=json.dumps(args)),
        PermissionManager(confirmation_channel=channel), None,
    )


@pytest.fixture
def outside(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "_read_allowed_roots", lambda: [tmp_path / "allowed"])
    first, second = tmp_path / "a.txt", tmp_path / "b.txt"
    first.write_text("ALFA ficticio", encoding="utf-8")
    second.write_text("BETA ficticio", encoding="utf-8")
    return first, second


@pytest.mark.parametrize("tool", ["ler_arquivo", "inspecionar_arquivo"])
def test_aud001_resolution_change_during_confirmation_is_rejected(outside, monkeypatch, tool):
    first, second = outside
    state = {"path": first}
    resolver = lambda value: state["path"]
    monkeypatch.setattr(permissions, "_resolve_path", resolver)
    monkeypatch.setattr(files, "_resolve_path", resolver)
    channel = Decision(lambda: state.update(path=second))
    result = execute(first, channel, tool)
    assert not result.ok
    assert len(channel.requests) == 1
    assert "BETA" not in str(result.data)


@pytest.mark.parametrize("tool", ["ler_arquivo", "inspecionar_arquivo"])
def test_aud001_replacement_at_same_path_is_rejected(outside, tool):
    first, second = outside
    channel = Decision(lambda: second.replace(first))
    result = execute(first, channel, tool)
    assert not result.ok
    assert len(channel.requests) == 1


@pytest.mark.parametrize("tool", ["ler_arquivo", "inspecionar_arquivo"])
def test_aud001_replacement_at_open_is_rejected(outside, monkeypatch, tool):
    first, second = outside
    original_open = Path.open
    replaced = []

    def racing_open(path, *args, **kwargs):
        if path == first and not replaced:
            second.replace(first)
            replaced.append(True)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", racing_open)
    result = execute(first, Decision(), tool)
    assert replaced
    assert not result.ok


@pytest.mark.parametrize("tool", ["ler_arquivo", "inspecionar_arquivo"])
def test_aud001_same_identity_still_works(outside, tool):
    first, _ = outside
    channel = Decision()
    result = execute(first, channel, tool)
    assert result.ok
    assert len(channel.requests) == 1
    assert repr(str(first)) in channel.requests[0].action


@pytest.mark.parametrize("tool", ["ler_arquivo", "inspecionar_arquivo"])
def test_aud001_denial_never_opens_file(outside, monkeypatch, tool):
    first, _ = outside
    def forbidden(*args, **kwargs):
        pytest.fail("conteudo aberto apos negativa")
    monkeypatch.setattr(Path, "open", forbidden)
    result = execute(first, Decision(approved=False), tool)
    assert not result.ok
