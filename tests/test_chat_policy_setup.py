"""Offline regression for chat-issued Windows runner authorization.

Windows-only tests operate on a temporary fake policy; no real user files,
GitHub credentials, runner processes or workflows are touched.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts/instalar/AUTORIZAR_TESTES_CHAT.ps1"
FUNCTIONS = ROOT / "remote_tests/chat-control-functions.ps1"
WORKFLOW = ROOT / ".github/workflows/auren-chat-tests.yml"
PINNED_BLOB = "90e3e3070f8b977bc328dc6ad72b112407ffeb3d"
KNOWN_SHA = "a" * 40

ORIGINAL_BLOCK = """    Test-RemoteControlRequest -Context $context -Event $event -Approval $approval -Elevated $elevated -Stopped $stopped
    if ($event.inputs.operacao -ceq 'testar_pr') {
        $resolved = Get-ResolvedReviewedPrSha -RunId $env:GITHUB_RUN_ID -Attempt $env:GITHUB_RUN_ATTEMPT -PrNumber $event.inputs.numero_pr
        Test-RemoteControlRequest -Context $context -Event $event -Approval $approval -Elevated $elevated -Stopped $stopped -ResolvedPrSha $resolved
    }"""


def test_permanent_workflow_and_policy_pins_match():
    import hashlib
    blob = WORKFLOW.read_bytes()
    actual = hashlib.sha1(b"blob " + str(len(blob)).encode() + b"\\0" + blob).hexdigest()
    assert actual == PINNED_BLOB
    assert PINNED_BLOB in FUNCTIONS.read_text(encoding="utf-8")
    assert PINNED_BLOB in INSTALLER.read_text(encoding="utf-8")
    assert "ref: b695fad7cc668d9a47e4dfc72f11a74b152d9cac" in WORKFLOW.read_text(encoding="utf-8")


def test_old_manual_control_is_not_changed_in_repo():
    assert "Test-RemoteControlRequest" in INSTALLER.read_text(encoding="utf-8")
    assert ORIGINAL_BLOCK in INSTALLER.read_text(encoding="utf-8")


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell tests require Windows")
def test_installer_preserves_old_hook_and_is_idempotent(tmp_path):
    policy = tmp_path / "auren-remote/policy"
    policy.mkdir(parents=True)
    old = "$ErrorActionPreference = 'Stop'\ntry {\n" + ORIGINAL_BLOCK + "\n} catch { exit 1 }\n"
    (policy / "before-job.ps1").write_text(old, encoding="utf-8")
    (policy / "remote-control-functions.ps1").write_text("function Test-RemoteControlRequest { }", encoding="utf-8")
    (policy / "control-approval.json").write_text('{"enabled":true}', encoding="utf-8")
    env = dict(os.environ, USERPROFILE=str(tmp_path))
    run = lambda: subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(INSTALLER)],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=25, check=False,
    )
    first = run()
    assert first.returncode == 0, first.stdout + "\n" + first.stderr
    installed = (policy / "before-job.ps1").read_text(encoding="utf-8")
    assert "Test-ChatControlRequest" in installed
    assert "Test-RemoteControlRequest" in installed
    assert "Get-ResolvedReviewedPrSha" in installed
    assert (policy / "before-job.pre-chat.bak").read_text(encoding="utf-8") == old
    approval = json.loads((policy / "chat-control-approval.json").read_text(encoding="utf-8"))
    assert approval == {"enabled": True, "workflow_blob": PINNED_BLOB}
    second = run()
    assert second.returncode == 0, second.stdout + "\n" + second.stderr


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell tests require Windows")
def test_local_guard_only_accepts_exact_owner_pr_commit(tmp_path):
    gh = tmp_path / "auren-remote/gh/bin/gh.exe"
    gh.parent.mkdir(parents=True)
    gh.write_text("dummy", encoding="utf-8")  # checked with Test-Path; never run
    event = {
        "action": "created",
        "repository": {
            "private": True, "full_name": "Yamatosemj/aurenOFC", "owner": {"login": "Yamatosemj"},
        },
        "sender": {"login": "Yamatosemj"},
        "comment": {
            "user": {"login": "Yamatosemj"},
            "body": "AUREN_TESTE_V1 pytest " + KNOWN_SHA,
        },
        "issue": {"number": 108, "pull_request": {"url": "https://example.invalid"}},
    }
    pr = {
        "number": 108, "state": "open", "draft": False,
        "base": {"ref": "main", "repo": {"full_name": "Yamatosemj/aurenOFC"}},
        "head": {"sha": KNOWN_SHA, "repo": {"full_name": "Yamatosemj/aurenOFC"}},
    }
    context = {
        "repository": "Yamatosemj/aurenOFC",
        "event_name": "issue_comment",
        "ref": "refs/heads/main",
        "workflow_ref": "Yamatosemj/aurenOFC/.github/workflows/auren-chat-tests.yml@refs/heads/main",
        "actor": "Yamatosemj", "triggering_actor": "Yamatosemj",
        "sha": KNOWN_SHA, "workflow_sha": KNOWN_SHA,
    }
    # JSON comes from fixed fixture constants, not user-supplied shell text.
    script = r"""
$ErrorActionPreference = 'Stop'
$env:GITHUB_JOB = 'executar'
. '__POLICY__'
function Invoke-BoundedLocalTool {
    param([string]$Executable,[string]$Arguments,[string]$InputText,[string]$Token)
    if ($Arguments -like '*credential fill*') { return "password=fakecredential`n" }
    if ($Arguments -like '*contents/.github/workflows/auren-chat-tests.yml*') { return '__BLOB__' }
    if ($Arguments -like '*pulls/108*') { return '__PR__' }
    if ($Arguments -like '*actions/runs/*/jobs*') {
        return '{"jobs":[{"name":"validar","conclusion":"success"}]}'
    }
    throw 'Unexpected network request'
}
$ctx = '__CTX__' | ConvertFrom-Json
$ev = '__EVENT__' | ConvertFrom-Json
$approval = '{"enabled":true,"workflow_blob":"__BLOB__"}' | ConvertFrom-Json
Test-ChatControlRequest -Context $ctx -Event $ev -ChatApproval $approval -Elevated $false -Stopped $false -RunId '123' -Attempt '1'
$ev.comment.body = 'AUREN_TESTE_V1 pytest ' + ('b' * 40)
try {
    Test-ChatControlRequest -Context $ctx -Event $ev -ChatApproval $approval -Elevated $false -Stopped $false -RunId '123' -Attempt '1'
    throw 'Accepted mismatched SHA'
} catch {
    if ($_.Exception.Message -eq 'Accepted mismatched SHA') { throw }
}
"""
    script = (script.replace("__POLICY__", str(FUNCTIONS).replace("'", "''"))
                    .replace("__BLOB__", PINNED_BLOB)
                    .replace("__PR__", json.dumps(pr))
                    .replace("__CTX__", json.dumps(context))
                    .replace("__EVENT__", json.dumps(event)))
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "-"],
        input=script, env=dict(os.environ, USERPROFILE=str(tmp_path)),
        capture_output=True, text=True, timeout=25, check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "Politica do chat aprovada" in result.stdout
