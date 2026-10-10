"""Exercise the explicit offline opt-in installer in real hosted Windows PowerShell.

Test policies live in pytest temporary directories, never on the personal PC.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts/instalar/AUTORIZAR_TESTES_CHAT_SEM_GCM.ps1"
OFFLINE_POLICY = ROOT / "remote_tests/chat-control-functions.ps1"
BLOB = "52abfd109c06cdc458727337579984d91da879bc"

OLDER_POLICY = (
    "function Test-ChatControlRequest {\n"
    "    if ($Elevated) { throw 'Runner elevado ou parada de emergencia ativa.' }\n"
    "    $workflowBlob = '" + BLOB + "'\n"
    "    Invoke-BoundedLocalTool -Executable 'git.exe' -Arguments 'credential fill'\n"
    "}\n"
)


def fixture_policy(tmp_path: Path, *, enabled: bool = True) -> Path:
    path = tmp_path / "auren-remote/policy"
    path.mkdir(parents=True)
    (path / "chat-control-functions.ps1").write_text(OLDER_POLICY, encoding="utf-8")
    (path / "before-job.ps1").write_text("Test-ChatControlRequest\n", encoding="utf-8")
    (path / "chat-control-approval.json").write_text(
        json.dumps({"enabled": enabled, "workflow_blob": BLOB}), encoding="utf-8"
    )
    return path


def invoke(tmp_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
         "Bypass", "-File", str(INSTALLER)],
        env=dict(os.environ, USERPROFILE=str(tmp_path)),
        cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=30, check=False,
    )


def test_offline_installer_requires_explicit_new_local_approval():
    src = OFFLINE_POLICY.read_text(encoding="utf-8")
    installer = INSTALLER.read_text(encoding="utf-8")
    assert "offline_hosted_validation -ne $true" in src
    assert "Name $offlineMarker -Value $true" in installer
    assert "Invoke-BoundedLocalTool" not in src


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows PowerShell")
def test_installer_opt_in_success_and_idempotency(tmp_path):
    path = fixture_policy(tmp_path)
    result = invoke(tmp_path)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "Autorizacao offline instalada" in result.stdout
    assert (path / "chat-control-functions.ps1").read_text(encoding="utf-8") == (
        OFFLINE_POLICY.read_text(encoding="utf-8")
    )
    assert (path / "chat-control-functions.pre-offline.bak").read_text(
        encoding="utf-8"
    ) == OLDER_POLICY
    assert (path / "before-job.ps1").read_text(encoding="utf-8") == (
        "Test-ChatControlRequest\n"
    )
    approval = json.loads((path / "chat-control-approval.json").read_text())
    assert approval["enabled"] is True
    assert approval["workflow_blob"] == BLOB
    assert approval["offline_hosted_validation"] is True
    old_approval = json.loads(
        (path / "chat-control-approval.pre-offline.bak").read_text()
    )
    assert "offline_hosted_validation" not in old_approval
    repeat = invoke(tmp_path)
    assert repeat.returncode == 0, repeat.stdout + "\n" + repeat.stderr
    assert "Autorizacao sem GCM ja instalada" in repeat.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows PowerShell")
def test_installer_does_not_touch_unapproved_policy(tmp_path):
    path = fixture_policy(tmp_path, enabled=False)
    result = invoke(tmp_path)
    assert result.returncode != 0
    assert (path / "chat-control-functions.ps1").read_text(encoding="utf-8") == OLDER_POLICY
    assert not (path / "chat-control-functions.pre-offline.bak").exists()
    assert not (path / "chat-control-approval.pre-offline.bak").exists()
