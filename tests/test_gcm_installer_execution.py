"""Regression: exercise the actual one-time Git/GCM installer in hosted Windows.

The installer runs against a temporary simulated runner policy only.
No real user policy, approvals, Git credential or GitHub API is touched.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "instalar" / "CORRIGIR_CREDENCIAL_CHAT.ps1"
GUARD = ROOT / "remote_tests" / "chat-control-functions.ps1"
BLOB = "90e3e3070f8b977bc328dc6ad72b112407ffeb3d"

# This is a minimal local policy fixture using the exact invariants checked by
# the installer. Crucially, the policy does NOT contain the new $gitArgs marker.
PRIOR_POLICY = (
    "function Test-ChatControlRequest {\n"
    "  if ($Elevated) { throw 'Runner elevado ou parada de emergencia ativa.' }\n"
    "  $workflowBlob = '" + BLOB + "'\n"
    "  $credential = '-c credential.interactive=never credential fill'\n"
    "}\n"
)


def prepare_temp_runner(tmp_path: Path, *, enabled: bool = True) -> Path:
    policy = tmp_path / "auren-remote" / "policy"
    policy.mkdir(parents=True)
    (policy / "before-job.ps1").write_text(
        "Test-ChatControlRequest\n", encoding="utf-8"
    )
    (policy / "chat-control-functions.ps1").write_text(
        PRIOR_POLICY, encoding="utf-8"
    )
    (policy / "chat-control-approval.json").write_text(
        json.dumps({"enabled": enabled, "workflow_blob": BLOB}),
        encoding="utf-8",
    )
    return policy


def invoke_installer(tmp_path: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["USERPROFILE"] = str(tmp_path)
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive",
         "-ExecutionPolicy", "Bypass", "-File", str(INSTALLER)],
        env=env, cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30, check=False,
    )


def test_installer_text_uses_exact_git_credential_name():
    code = INSTALLER.read_text(encoding="utf-8")
    assert '$marker = "credential.interactive=never credential fill"' in code
    assert 'credencial.interactive=never' not in code
    assert "WriteAllText($hook" not in code
    assert "WriteAllText($approvalFile" not in code


@pytest.mark.skipif(sys.platform != "win32", reason="Needs Windows PowerShell")
def test_historical_gcm_installer_fails_closed_with_offline_policy_source(tmp_path):
    policy = prepare_temp_runner(tmp_path)
    first = invoke_installer(tmp_path)
    assert first.returncode != 0  # Historical installer must not install offline gate by mistake.
    assert (policy / "chat-control-functions.ps1").read_text(
        encoding="utf-8"
    ) == PRIOR_POLICY
    assert not (policy / "chat-control-functions.pre-gcm-cwd.bak").exists()

@pytest.mark.skipif(sys.platform != "win32", reason="Needs Windows PowerShell")
def test_installer_rejects_unapproved_policy_without_mutation(tmp_path):
    policy = prepare_temp_runner(tmp_path, enabled=False)
    result = invoke_installer(tmp_path)
    assert result.returncode != 0
    assert (policy / "chat-control-functions.ps1").read_text(
        encoding="utf-8"
    ) == PRIOR_POLICY
    assert not (policy / "chat-control-functions.pre-gcm-cwd.bak").exists()
