"""Run the ASCII-workflow opt-in migrator on an isolated Windows fixture."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts/instalar/ATUALIZAR_WORKFLOW_CHAT_ASCII.ps1"
POLICY = ROOT / "remote_tests/chat-control-functions.ps1"
WORKFLOW = ROOT / ".github/workflows/auren-chat-tests.yml"
OLD = "90e3e3070f8b977bc328dc6ad72b112407ffeb3d"
NEW = "52abfd109c06cdc458727337579984d91da879bc"

OLD_POLICY = (
    "function Test-ChatControlRequest {\n"
    "    if ($Elevated) { throw 'Runner elevado ou parada de emergencia ativa.' }\n"
    f"    $workflowBlob = '{OLD}'\n"
    "    $ChatApproval.offline_hosted_validation = $true\n"
    "}\n"
)


def prepare(tmp_path: Path, *, enabled: bool = True, offline: bool = True) -> Path:
    path = tmp_path / "auren-remote/policy"
    path.mkdir(parents=True)
    (path / "chat-control-functions.ps1").write_text(OLD_POLICY, encoding="utf-8")
    (path / "before-job.ps1").write_text("Test-ChatControlRequest\n", encoding="utf-8")
    (path / "chat-control-approval.json").write_text(json.dumps({
        "enabled": enabled, "workflow_blob": OLD, "offline_hosted_validation": offline
    }), encoding="utf-8")
    return path


def run_installer(tmp_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
         "Bypass", "-File", str(INSTALLER)],
        cwd=ROOT, env=dict(os.environ, USERPROFILE=str(tmp_path)),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=30, check=False,
    )


def test_workflow_blob_includes_ascii_safe_summary():
    import hashlib

    blob = WORKFLOW.read_bytes().replace(b"\r\n", b"\n")
    actual = hashlib.sha1(b"blob " + str(len(blob)).encode() + b"\0" + blob).hexdigest()
    assert actual == NEW
    assert OLD != NEW
    assert '### Auren no Windows - PR' in WORKFLOW.read_text(encoding="utf-8")
    assert '### Auren no Windows — PR' not in WORKFLOW.read_text(encoding="utf-8")
    assert NEW in POLICY.read_text(encoding="utf-8")
    assert OLD in INSTALLER.read_text(encoding="utf-8")
    assert NEW in INSTALLER.read_text(encoding="utf-8")


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows PowerShell")
def test_real_powershell_installer_success_backup_and_idempotence(tmp_path):
    path = prepare(tmp_path)
    first = run_installer(tmp_path)
    assert first.returncode == 0, first.stdout + "\n" + first.stderr
    assert "Workflow ASCII autorizado" in first.stdout
    assert (path / "chat-control-functions.ps1").read_text(encoding="utf-8") == (
        POLICY.read_text(encoding="utf-8")
    )
    assert (path / "chat-control-functions.pre-ascii-workflow.bak").read_text(
        encoding="utf-8"
    ) == OLD_POLICY
    assert (path / "before-job.ps1").read_text(encoding="utf-8") == (
        "Test-ChatControlRequest\n"
    )
    approval = json.loads((path / "chat-control-approval.json").read_text())
    assert approval == {
        "enabled": True, "workflow_blob": NEW, "offline_hosted_validation": True
    }
    old_approval = json.loads(
        (path / "chat-control-approval.pre-ascii-workflow.bak").read_text()
    )
    assert old_approval["workflow_blob"] == OLD
    second = run_installer(tmp_path)
    assert second.returncode == 0, second.stdout + "\n" + second.stderr
    assert "ja instalada" in second.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows PowerShell")
@pytest.mark.parametrize("enabled,offline", [(False, True), (True, False)])
def test_installer_refuses_unapproved_policy_without_mutation(tmp_path, enabled, offline):
    path = prepare(tmp_path, enabled=enabled, offline=offline)
    proc = run_installer(tmp_path)
    assert proc.returncode != 0
    assert (path / "chat-control-functions.ps1").read_text(encoding="utf-8") == OLD_POLICY
    approval = json.loads((path / "chat-control-approval.json").read_text())
    assert approval["enabled"] is enabled
    assert approval["offline_hosted_validation"] is offline
    assert approval["workflow_blob"] == OLD
    assert not (path / "chat-control-functions.pre-ascii-workflow.bak").exists()
    assert not (path / "chat-control-approval.pre-ascii-workflow.bak").exists()
