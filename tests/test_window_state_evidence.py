from types import SimpleNamespace
import pytest
from tools import windows_window as windows
from core.harness_completion import _mensagem_conclusao_local


@pytest.mark.parametrize('name,state,command', [
    ('maximizar_janela_windows', 'maximizada', 3),
    ('minimizar_janela_windows', 'minimizada', 6),
    ('restaurar_janela_windows', 'normal', 1),
])
def test_state_comes_from_observation_even_when_showwindow_returns_false(monkeypatch, name, state, command):
    calls = []
    api = SimpleNamespace(ShowWindow=lambda *args: calls.append(args) or False,
        IsWindow=lambda _: True, IsIconic=lambda _: state == 'minimizada',
        IsZoomed=lambda _: state == 'maximizada')
    monkeypatch.setattr(windows, '_user32', lambda: api)
    monkeypatch.setattr(windows, '_encontrar_janela_windows', lambda _: (42,'Fixture'))
    monkeypatch.setattr(windows.os, 'name', 'nt')
    result = getattr(windows, name)('Fixture')
    assert result.ok and result.data['window_state']['observed'] == state
    assert result.data['window_state']['verified'] is True
    assert calls == [(42,command)]
    assert _mensagem_conclusao_local('fixture', name, str(result),
        terminal_result_tools={name}, multietapa_browser=False) == result.message


@pytest.mark.parametrize('disappeared', [False, True])
def test_unverified_state_cannot_be_success(monkeypatch, disappeared):
    api = SimpleNamespace(ShowWindow=lambda *_: True, IsWindow=lambda _: not disappeared,
        IsIconic=lambda _: False, IsZoomed=lambda _: False)
    monkeypatch.setattr(windows, '_user32', lambda: api)
    monkeypatch.setattr(windows, '_encontrar_janela_windows', lambda _: (42,'Fixture'))
    monkeypatch.setattr(windows.os, 'name', 'nt')
    times = iter([0,1])
    monkeypatch.setattr(windows.time, 'monotonic', lambda: next(times))
    result = windows.maximizar_janela_windows('Fixture')
    assert not result.ok
    assert result.error_code == ('window_disappeared' if disappeared else 'window_state_unverified')


def test_api_error_cannot_claim_normal_state(monkeypatch):
    def fail(_):
        raise OSError('PRIVATE')
    api = SimpleNamespace(ShowWindow=lambda *_: True, IsWindow=lambda _: True, IsIconic=fail)
    monkeypatch.setattr(windows, '_user32', lambda: api)
    monkeypatch.setattr(windows, '_encontrar_janela_windows', lambda _: (42,'Fixture'))
    monkeypatch.setattr(windows.os, 'name', 'nt')
    result = windows.restaurar_janela_windows('Fixture')
    assert not result.ok and result.error_code == 'window_state_verification_error'
    assert 'PRIVATE' not in str(result)
