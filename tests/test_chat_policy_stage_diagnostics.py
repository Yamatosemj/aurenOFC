"""Controls for the explicit lower-friction offline Windows gate.

This deliberately shifts online PR validation to the GitHub-hosted validator.
It does not make an unfounded claim that local policy checks remote SHA.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "remote_tests/chat-control-functions.ps1"
ONLINE_INSTALLER = ROOT / "scripts/instalar/CORRIGIR_CREDENCIAL_CHAT.ps1"
OFFLINE_INSTALLER = ROOT / "scripts/instalar/AUTORIZAR_TESTES_CHAT_SEM_GCM.ps1"


def test_offline_policy_limits_owner_workflow_run_and_writes_no_secrets():
    guard = GUARD.read_text(encoding="utf-8")
    for marker in (
        "Runner elevado ou parada de emergencia ativa.",
        "ChatApproval.offline_hosted_validation -ne $true",
        "$Context.workflow_ref -cne $workflow",
        "$Context.actor -cne $owner",
        "$Context.triggering_actor -cne $owner",
        "$Context.sha -cnotmatch",
        "$Context.workflow_sha -cne $Context.sha",
        "$env:GITHUB_JOB -cne 'executar'",
        "$Attempt -cne '1'",
        "$Event.repository.private -ne $true",
        "$Event.comment.user.login -cne $owner",
        "$Event.issue.pull_request",
        "$body -cmatch",
    ):
        assert marker in guard
    assert "Invoke-BoundedLocalTool" not in guard
    assert "credential fill" not in guard
    assert "GH_TOKEN" not in guard


def test_offline_installer_is_explicit_reversible_and_approval_scoped():
    code = OFFLINE_INSTALLER.read_text(encoding="utf-8")
    assert "Copy-Item -LiteralPath $target -Destination $backup" in code
    assert "Copy-Item -LiteralPath $approvalFile -Destination $approvalBackup" in code
    assert "WriteAllText($target" in code
    assert "WriteAllText($approvalFile" in code
    assert "WriteAllText($hook" not in code
    assert "Join-Path $policy 'control-approval.json'" not in code
    assert "ParseInput(" in code
    assert "offline_hosted_validation" in code
    assert ONLINE_INSTALLER.exists()
