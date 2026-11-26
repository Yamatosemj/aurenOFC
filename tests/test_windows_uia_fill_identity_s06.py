"""Regressoes offline da identidade autorizada para preenchimento UIA."""

import json
import shutil
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.permission_manager import PermissionManager
from tools import dispatcher, windows, windows_uia


class _Confirmation:
    def __init__(self, approve=False):
        self.approve = approve
        self.requests = []

    def confirmar(self, request):
        self.requests.append(request)
        return self.approve


def _fill(target, before, after, *, approve=False, execution_hwnd=100):
    """Two snapshots of a synthetic window; the executor only records a simulated effect."""
    effects = []
    confirmation = _Confirmation(approve)

    def resolve(operation, payload):
        assert operation == "resolver"
        assert payload["hwnd"] == 100
        return {"ok": True, "nome": before["name"], "automation_id": before["id"],
                "tipo": "Edit", "protegido": before["protected"],
                "runtime_id": before["runtime"]}

    def execute(operation, payload):
        assert operation == "preencher"
        assert payload["alvo"] in {after["name"], after["id"]}
        expected = payload["identidade_esperada"]
        if (expected["runtime_id"] != after["runtime"]
                or expected["nome"] != after["name"]
                or expected["automation_id"] != after["id"]
                or expected["protegido"] != after["protected"]):
            return {"ok": False, "erro": "A identidade do controle UIA mudou apos a autorizacao."}
        if after["protected"] and not payload["permitir_protegido"]:
            return {"ok": False, "erro": "IsPassword exige confirmacao."}
        effects.append(after["runtime"])
        return {"ok": True, "resultado": "Efeito simulado.", "confirmado": True}

    item = SimpleNamespace(name="preencher_elemento_windows", arguments=json.dumps({
        "alvo_janela": "Janela sintetica", "alvo": target,
        "texto": "dado-inofensivo", "indice": 1,
    }))
    with (patch.object(windows, "_ui_automation_janela", return_value=(100, "Janela sintetica", None)),
          patch.object(windows, "_executar_ui_automation", side_effect=resolve),
          patch.object(windows_uia, "_ui_automation_janela", return_value=(execution_hwnd, "Janela sintetica", None)),
          patch.object(windows_uia, "_executar_ui_automation", side_effect=execute) as executor):
        result = dispatcher.executar_ferramenta(item, PermissionManager(confirmation_channel=confirmation), None)
    return result, effects, confirmation.requests, executor.call_count


def _control(name, automation_id, runtime, protected=False):
    return {"name": name, "id": automation_id, "runtime": runtime, "protected": protected}


def test_safe_field_same_identity_stays_automatic():
    control = _control("busca", "search-field", "1:2:3")
    result, effects, requests, calls = _fill("busca", control, control)
    assert result.ok and effects == ["1:2:3"] and requests == [] and calls == 1


def test_safe_field_same_name_different_control_is_rejected():
    result, effects, requests, calls = _fill(
        "busca", _control("busca", "field-a", "1:2:3"),
        _control("busca", "field-b", "1:2:4"),
    )
    assert not result.ok and effects == [] and requests == [] and calls == 1


def test_confirmed_password_reused_automation_id_is_rejected():
    result, effects, requests, calls = _fill(
        "senha", _control("senha", "shared-id", "1:2:3", True),
        _control("outra senha", "shared-id", "1:2:4", True), approve=True,
    )
    assert not result.ok and effects == [] and len(requests) == 1 and calls == 1


def test_safe_field_becoming_protected_is_rejected():
    result, effects, requests, calls = _fill(
        "busca", _control("busca", "field-a", "1:2:3"),
        _control("busca", "field-a", "1:2:4", True),
    )
    assert not result.ok and effects == [] and requests == [] and calls == 1


def test_same_protected_control_after_confirmation_is_allowed():
    control = _control("senha", "password-id", "1:2:3", True)
    result, effects, requests, calls = _fill("senha", control, control, approve=True)
    assert result.ok and effects == ["1:2:3"] and len(requests) == 1 and calls == 1


def test_changed_window_is_rejected_before_executor():
    control = _control("busca", "field-a", "1:2:3")
    result, effects, requests, calls = _fill("busca", control, control, execution_hwnd=101)
    assert not result.ok and effects == [] and requests == [] and calls == 0


def test_unavailable_runtime_id_is_rejected_before_authorization():
    control = _control("busca", "field-a", "")
    result, effects, requests, calls = _fill("busca", control, control)
    assert not result.ok and result.error_code == "uia_identity_unavailable"
    assert effects == [] and requests == [] and calls == 0


def test_inspection_fallback_keeps_runtime_identity():
    args = {"alvo_janela": "Janela sintetica", "alvo": "busca", "indice": 1}
    def fake_uia(operation, payload):
        if operation == "resolver":
            return {"ok": False, "erro": "falha sintetica"}
        assert operation == "inspecionar"
        return {"ok": True, "controles": [{"nome": "busca", "automation_id": "field-a",
                                             "tipo": "Edit", "protegido": False,
                                             "runtime_id": "1:2:3"}]}
    with (patch.object(windows, "_ui_automation_janela", return_value=(100, "Janela sintetica", None)),
          patch.object(windows, "_executar_ui_automation", side_effect=fake_uia)):
        result = dispatcher._resolver_ui_automation_para_permissao(args)
    assert result["ok"] and result["hwnd"] == 100 and result["runtime_id"] == "1:2:3"


def test_denied_password_confirmation_never_reaches_executor():
    control = _control("senha", "password-id", "1:2:3", True)
    result, effects, requests, calls = _fill("senha", control, control)
    assert not result.ok and effects == [] and len(requests) == 1 and calls == 0


def test_powershell_checks_identity_before_fill_effect():
    script = windows_uia._UI_AUTOMATION_POWERSHELL
    assert script.index("Assert-FillIdentity $item $payload.identidade_esperada") < script.index(
        "try { $item.Element.SetFocus() }"
    )
    assert "Assert-FillIdentity $freshItem $payload.identidade_esperada" in script
    assert "$focoRuntimeId -ceq [string]$payload.identidade_esperada.runtime_id" in script


def test_powershell_identity_guard_with_synthetic_elements():
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if not powershell:
        pytest.skip("PowerShell indisponivel neste ambiente")
    script = windows_uia._UI_AUTOMATION_POWERSHELL
    helpers = script[script.index("function Get-RuntimeIdString"):script.index("function Get-PatternNames")]
    probe = helpers + r'''
$element = [pscustomobject]@{}
$element | Add-Member ScriptMethod GetRuntimeId { return @(1,2,3) }
$item = [pscustomobject]@{ Element=$element; Name='busca'; AutomationId='field-a'; ControlType='Edit'; IsPassword=$false }
$expected = [pscustomobject]@{ runtime_id='1:2:3'; nome='busca'; automation_id='field-a'; tipo='Edit'; protegido=$false }
try { Assert-FillIdentity $item $expected; 'allow' } catch { 'deny' }
$expected.runtime_id = '1:2:4'
try { Assert-FillIdentity $item $expected; 'allow' } catch { 'deny' }
$expected.runtime_id = '1:2:3'
$expected.automation_id = 'field-b'
try { Assert-FillIdentity $item $expected; 'allow' } catch { 'deny' }
'''
    completed = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", probe],
        capture_output=True, text=True, timeout=15, check=True,
    )
    assert completed.stdout.splitlines() == ["allow", "deny", "deny"]
