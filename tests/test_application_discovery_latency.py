"""General Windows discovery regressions; no personal app is launched."""
import subprocess
from types import SimpleNamespace
import pytest
from tools import applications as apps


@pytest.fixture(autouse=True)
def clear_catalog(monkeypatch):
    monkeypatch.setattr(apps, '_catalog_cache', None)
    monkeypatch.setattr(apps, '_catalog_expires', 0)


def test_catalog_cache_is_short_lived_and_returns_copies(monkeypatch):
    calls, now = [], [10.0]
    monkeypatch.setattr(apps.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(apps, '_buscar_aplicativos_do_windows',
        lambda: calls.append(1) or [{'Name': 'Teste', 'AppID': 'test'}])
    apps.buscar_aplicativos_do_windows()[0]['AppID'] = 'changed'
    assert apps.buscar_aplicativos_do_windows()[0]['AppID'] == 'test'
    assert len(calls) == 1
    now[0] += 61
    apps.buscar_aplicativos_do_windows()
    assert len(calls) == 2


def test_empty_catalog_is_retried_after_installation(monkeypatch):
    responses = iter([[], [{'Name': 'Novo', 'AppID': 'new'}]])
    monkeypatch.setattr(apps, '_buscar_aplicativos_do_windows', lambda: next(responses))
    assert apps.buscar_aplicativos_do_windows() == []
    assert apps.buscar_aplicativos_do_windows()[0]['Name'] == 'Novo'


def test_path_hit_never_starts_recursive_powershell(tmp_path, monkeypatch):
    target = tmp_path/'Teste.exe'
    target.write_bytes(b'fixture, never executed')
    monkeypatch.setenv('PATH', str(tmp_path))
    monkeypatch.setattr(apps.subprocess, 'run', lambda *a, **k: pytest.fail('Unnecessary recursive scan'))
    assert apps.procurar_executavel('Teste') == str(target.resolve())


def test_recursive_scan_runs_once_for_all_names_and_roots(tmp_path, monkeypatch):
    for key in ('LOCALAPPDATA', 'PROGRAMFILES', 'PROGRAMFILES(X86)'):
        monkeypatch.setenv(key, str(tmp_path))
    monkeypatch.setattr(apps.shutil, 'which', lambda _: None)
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        assert kwargs['timeout'] == 20 and not kwargs.get('shell')
        return SimpleNamespace(returncode=0, stdout='')
    monkeypatch.setattr(apps.subprocess, 'run', run)
    assert apps.procurar_executavel('Programa Ficticio') is None
    assert len(calls) == 1
    assert 'programaficticio.exe' in calls[0][-1]
    assert 'programa_ficticio.exe' in calls[0][-1]


@pytest.mark.parametrize('failure,code', [
    (subprocess.TimeoutExpired('fixture', 20), 'application_search_timeout'),
    (PermissionError('fixture'), 'application_access_denied'),
])
def test_discovery_failure_is_structured(monkeypatch, failure, code):
    monkeypatch.setattr(apps, 'encontrar_aplicativo', lambda _: None)
    monkeypatch.setattr(apps, 'procurar_atalho', lambda _: None)
    def search(_):
        raise failure
    monkeypatch.setattr(apps, 'procurar_executavel', search)
    result = apps.abrir_programa('Ficticio')
    assert not result.ok and result.error_code == code


def test_catalog_timeout_can_fall_back_before_any_effect(monkeypatch):
    def search(_):
        raise subprocess.TimeoutExpired('fixture', 12)
    monkeypatch.setattr(apps, 'encontrar_aplicativo', search)
    monkeypatch.setattr(apps, 'procurar_atalho', lambda _: None)
    monkeypatch.setattr(apps, 'procurar_executavel', lambda _: r'C:\Fixture\Test.exe')
    monkeypatch.setattr(apps.subprocess, 'Popen', lambda *a, **k: SimpleNamespace(pid=42))
    result = apps.abrir_programa('Ficticio')
    assert result.ok and result.data['abertura_solicitada']
    assert result.data['janela_verificada'] is False


def test_uncertain_launch_does_not_launch_alternative(monkeypatch):
    monkeypatch.setattr(apps, 'encontrar_aplicativo', lambda _: {'Name': 'Teste', 'AppID': 'fixture'})
    def launch(*a, **k):
        raise OSError('unknown launch outcome')
    monkeypatch.setattr(apps.subprocess, 'Popen', launch)
    monkeypatch.setattr(apps, 'procurar_atalho', lambda _: pytest.fail('Second launch path'))
    result = apps.abrir_programa('Teste')
    assert not result.ok and result.error_code == 'application_launch_failed'


def test_missing_program_has_distinct_error(monkeypatch):
    for fn in ('encontrar_aplicativo', 'procurar_atalho', 'procurar_executavel'):
        monkeypatch.setattr(apps, fn, lambda _: None)
    assert apps.abrir_programa('Ficticio').error_code == 'application_not_found'
