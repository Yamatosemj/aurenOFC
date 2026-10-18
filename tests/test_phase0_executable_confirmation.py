"""Regressao de seguranca da Fase 0; nenhuma acao Windows real.

Contrato reconciliado: caminho explicito exige confirmacao. As falhas
anteriores a correcao estao preservadas no relatorio da Fase 0.
"""
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.permission_manager import PermissionManager
from core.tool_result import ToolResult
from tools import dispatcher


@pytest.mark.parametrize('target', [
    r'C:\AurenFicticio\Editor.exe',
    '"C:\\Auren Ficticio\\Editor.exe"',
    r'\\servidor-ficticio\compartilhamento\Editor.exe',
    "'C:\\Auren Ficticio\\Editor.exe'",
    r'.\Editor.exe',
    './Editor.exe',
    r'C:Editor.exe',
])
def test_absolute_executable_cannot_run_after_confirmation_denial(target):
    asked, executed = [], []
    manager = PermissionManager(confirmation_channel=SimpleNamespace(
        confirmar=lambda request: asked.append(request) or False))
    item = SimpleNamespace(name='abrir_programa', arguments=json.dumps({'programa': target}))
    with patch.dict(dispatcher.TOOL_HANDLERS, {'abrir_programa':
        lambda *args: executed.append(args) or ToolResult.success('Efeito simulado.')}):
        result = dispatcher.executar_ferramenta(item, manager, None)
    assert (len(asked), len(executed), result.ok) == (1, 0, False), (
        'Confirmacoes, efeitos simulados, sucesso:', len(asked), len(executed), result.ok)
    assert result.error_code == 'permission_denied'


def test_ordinary_app_name_keeps_existing_auto_policy():
    executed = []
    manager = PermissionManager(confirmation_channel=SimpleNamespace(
        confirmar=lambda request: pytest.fail('Nome comum nao deve pedir confirmacao neste controle.')))
    item = SimpleNamespace(name='abrir_programa', arguments='{"programa":"Calculadora"}')
    with patch.dict(dispatcher.TOOL_HANDLERS, {'abrir_programa':
        lambda *args: executed.append(args) or ToolResult.success('Efeito simulado.')}):
        result = dispatcher.executar_ferramenta(item, manager, None)
    assert result.ok and len(executed) == 1


@pytest.mark.parametrize('quote', ['', '"', "'"])
def test_explicit_file_after_simulated_confirmation_preserves_exact_path(tmp_path, monkeypatch, quote):
    from tools import applications
    target = tmp_path / 'Pasta Ficticia' / 'Editor.exe'
    target.parent.mkdir()
    target.write_bytes(b'arquivo ficticio, nao executavel')
    events = []
    def confirm(request):
        events.append('confirmacao simulada')
        return True
    def launch(args, **kwargs):
        events.append(args)
        assert not kwargs.get('shell', False)
        return SimpleNamespace(pid=742)
    def forbid_search(*args):
        pytest.fail('Caminho explicito nao pode usar busca aproximada.')
    monkeypatch.setattr(applications, 'encontrar_aplicativo', forbid_search)
    monkeypatch.setattr(applications.subprocess, 'Popen', launch)
    manager = PermissionManager(confirmation_channel=SimpleNamespace(confirmar=confirm))
    item = SimpleNamespace(name='abrir_programa',
        arguments=json.dumps({'programa': quote + str(target) + quote}))
    result = dispatcher.executar_ferramenta(item, manager, None)
    assert events == ['confirmacao simulada', [str(target.resolve())]]
    assert result.ok and result.data['pid'] == 742
    assert result.data['abertura_solicitada'] is True
    assert 'ainda nao foi verificada' in result.message


@pytest.mark.parametrize('kind', ['missing', 'directory', 'extension', 'launch_error'])
def test_invalid_explicit_target_never_falls_back_or_reports_success(tmp_path, monkeypatch, kind):
    from tools import applications
    target = tmp_path / ('Editor.bat' if kind == 'extension' else 'Editor.exe')
    if kind == 'directory':
        target.mkdir()
    elif kind != 'missing':
        target.write_bytes(b'ficticio')
    launches = []
    def launch(*args, **kwargs):
        launches.append(args)
        raise OSError('falha ficticia ao iniciar')
    monkeypatch.setattr(applications.subprocess, 'Popen', launch)
    monkeypatch.setattr(applications, 'encontrar_aplicativo',
        lambda *_: pytest.fail('Nao substituir um alvo invalido por outro aplicativo.'))
    result = applications.abrir_programa(str(target))
    assert not result.ok
    assert len(launches) == (1 if kind == 'launch_error' else 0)
