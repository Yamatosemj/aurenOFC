"""The Windows hook must expose the failing stage without exposing secrets."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "remote_tests/chat-control-functions.ps1"
INSTALLER = ROOT / "scripts/instalar/DIAGNOSTICAR_TESTES_CHAT.ps1"
LEGACY = ROOT / "scripts/instalar/AUTORIZAR_TESTES_CHAT.ps1"

def test_local_guard_keeps_the_original_protection_and_identifies_failures():
    source = GUARD.read_text(encoding="utf-8")
    assert source.count("Invoke-BoundedLocalTool -Executable") == 4
    assert source.count("catch {") == 4
    for marker in (
        "Etapa credencial Git/GCM indisponivel no contexto do runner.",
        "Etapa consultar conteudo SHA do workflow falhou no runner.",
        "Etapa consultar PR via GitHub API falhou no runner.",
        "Etapa consultar validacao hospedada via GitHub API falhou no runner.",
    ):
        assert source.count(marker) == 1
    assert "$workflowBlob = '90e3e3070f8b977bc328dc6ad72b112407ffeb3d'" in source
    assert "Runner elevado ou parada de emergencia ativa" in source
    assert "if ($pr.head.sha -cne $prSha)" not in source  # SHA lives in the compound guard
    assert "$pr.head.sha -cne $prSha" in source
    assert "$validation.Count -ne 1" in source


def test_diagnostic_installer_does_not_edit_old_hook_or_approvals():
    src = INSTALLER.read_text(encoding="utf-8")
    assert "Copy-Item -LiteralPath $target -Destination $backup" in src
    assert "[IO.File]::WriteAllText($target, $replacement" in src
    assert "WriteAllText($hook" not in src
    assert "WriteAllText($approvalFile" not in src
    assert "Test-ChatControlRequest" in src
    assert "ParseInput(" in src
    assert LEGACY.exists()
