from types import SimpleNamespace
import os
import pytest
from tools import applications as apps


def test_exact_exe_launch_skips_catalog_and_all_scans(tmp_path, monkeypatch):
    target = tmp_path/'Fixture.exe'
    target.write_bytes(b'not executed')
    monkeypatch.setenv('PATH', str(tmp_path))
    for name in ('encontrar_aplicativo', 'procurar_atalho', 'procurar_executavel'):
        monkeypatch.setattr(apps, name, lambda *_: pytest.fail('Unnecessary discovery'))
    launches = []
    monkeypatch.setattr(apps.subprocess, 'Popen', lambda argv, **_: launches.append(argv) or SimpleNamespace(pid=42))
    result = apps.abrir_programa('Fixture.exe')
    assert launches == [[str(target.resolve())]]
    assert result.ok and result.data['source'] == 'path'
    assert result.data['janela_verificada'] is False


def test_implicit_cwd_relative_path_and_pathext_are_not_executed(tmp_path, monkeypatch):
    (tmp_path/'Fixture.exe').write_bytes(b'never executed')
    (tmp_path/'Only.cmd').write_text('never executed')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('PATH', os.pathsep.join(('', '.', str(tmp_path))))
    assert apps._executavel_exato_path('Fixture.exe') is None
    assert apps._executavel_exato_path('Only.cmd') is None


def test_exact_path_failure_never_falls_back_to_another_launch(tmp_path, monkeypatch):
    (tmp_path/'Fixture.exe').write_bytes(b'never executed')
    monkeypatch.setenv('PATH', str(tmp_path))
    def fail(*_, **__):
        raise OSError('uncertain')
    monkeypatch.setattr(apps.subprocess, 'Popen', fail)
    monkeypatch.setattr(apps, 'encontrar_aplicativo', lambda *_: pytest.fail('Second launch'))
    assert apps.abrir_programa('Fixture.exe').error_code == 'application_launch_failed'


def test_recursive_names_preserve_exe_suffix_and_roots_do_not_overlap(tmp_path, monkeypatch):
    (tmp_path/'Programs').mkdir()
    for key in ('LOCALAPPDATA', 'PROGRAMFILES', 'PROGRAMFILES(X86)'):
        monkeypatch.setenv(key, str(tmp_path))
    monkeypatch.setenv('PATH', '')
    commands = []
    monkeypatch.setattr(apps.subprocess, 'run', lambda argv, **_: commands.append(argv[-1]) or SimpleNamespace(returncode=0, stdout=''))
    assert apps.procurar_executavel('Fixture.exe') is None
    assert 'Fixture.exe' in commands[0]
    assert 'exe.exe' not in commands[0] and 'fixtureexe.exe' not in commands[0]
    assert str(tmp_path/'Programs') not in commands[0]


def test_tied_catalog_is_not_an_arbitrary_launch(monkeypatch):
    monkeypatch.setattr(apps, 'buscar_aplicativos_do_windows', lambda: [
        {'Name':'Fixture One','AppID':'one'}, {'Name':'Fixture Two','AppID':'two'}])
    monkeypatch.setattr(apps.subprocess, 'Popen', lambda *_a, **_k: pytest.fail('Ambiguous launch'))
    assert apps.abrir_programa('Fixture').error_code == 'application_ambiguous'


def test_duplicate_exact_catalog_names_need_disambiguation(monkeypatch):
    monkeypatch.setattr(apps, 'buscar_aplicativos_do_windows', lambda: [
        {'Name':'Fixture','AppID':'one'}, {'Name':'Fixture','AppID':'two'}])
    monkeypatch.setattr(apps.subprocess, 'Popen', lambda *_a, **_k: pytest.fail('Ambiguous exact launch'))
    assert apps.abrir_programa('Fixture').error_code == 'application_ambiguous'
