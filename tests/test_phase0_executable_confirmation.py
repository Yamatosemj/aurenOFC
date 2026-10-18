"""Regressao de seguranca da Fase 0; nenhuma acao Windows real.

Contrato da PR #152: caminho absoluto exige confirmacao. No HEAD revisado
da #153 estes tres casos falham. Nao representam uma correcao implementada.
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
