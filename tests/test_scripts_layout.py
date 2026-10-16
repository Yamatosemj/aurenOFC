"""Regressao: atalhos Windows devem funcionar a partir da nova organizacao."""
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
BAT_FILES = {
    "iniciar/ABRIR_AUREN_GUI.bat": "interface_auren.py",
    "iniciar/AUREN_VOZ.bat": "voice\\main.py",
    "iniciar/AUREN_CHROME.bat": "ui\\chrome_server.py",
    "instalar/INSTALAR_AUREN.bat": "requirements.txt",
    "instalar/INSTALAR_VOZ.bat": "requirements-voice.txt",
    "testar/TESTAR_AUREN.bat": "testes_auren.py",
    "testar/TESTAR_VOZ.bat": "tests\\test_voice.py",
    "diagnosticos/AUREN_LISTAR_MICROFONES.bat": "voice\\list_devices.py",
    "diagnosticos/MEDIR_METRICAS_ROUTER.bat": "medir_metricas_router.py",
    "diagnosticos/MEDIR_ROUTER_BASELINE.bat": "medir_router_baseline.py",
    "experimentos/ATIVAR_EXPERIMENTO_AUDIO.bat": "main.py",
    "experimentos/DESATIVAR_EXPERIMENTO_AUDIO.bat": "main.py",
}


def test_batch_files_are_sorted_outside_root():
    assert not list(ROOT.glob("*.bat"))
    assert sorted(str(p.relative_to(SCRIPTS)).replace("\\", "/") for p in SCRIPTS.rglob("*.bat")) == sorted(BAT_FILES)


def test_all_batch_launchers_return_to_repository_root_before_execution():
    for relative, target in BAT_FILES.items():
        content = (SCRIPTS / relative).read_text(encoding="utf-8")
        lines = content.splitlines()
        assert lines[0].lower() == "@echo off"
        assert any(re.fullmatch(r'cd /d "%~dp0\.\.\\\.\."', line, re.I) for line in lines[:4]), relative
        assert target in content, relative
        assert (ROOT / target.replace("\\", "/")).is_file(), relative


def test_relocated_diagnostic_python_scripts_have_project_bootstrap():
    for name in ("medir_custo_modelo.py", "medir_capability_audio_experiment.py", "testar_spotify_desktop_runtime.py"):
        path = SCRIPTS / "diagnosticos" / name
        assert path.is_file()
        source = path.read_text(encoding="utf-8")
        compile(source, str(path), "exec")
        assert not (ROOT / name).exists()


def test_runtime_entrypoints_and_live_test_facades_are_preserved():
    for entrypoint in ("auren.py", "main.py", "interface_auren.py", "testes_auren.py", "testes_auren_live.py", "medir_metricas_router.py", "medir_router_baseline.py"):
        assert (ROOT / entrypoint).is_file()


def test_default_test_shortcut_does_not_run_live_or_desktop_layers():
    """Regressao da auditoria: dar duplo clique no BAT nao ativa L2/L4/L5."""
    shortcut = (SCRIPTS / "testar" / "TESTAR_AUREN.bat").read_text(encoding="utf-8")
    # Capturamos apenas o bloco de selecao sem argumentos; comentarios sobre
    # outras camadas nao devem produzir falso positivo no teste.
    match = re.search(
        r'if "%~1"==""\s*\((.*?)\n\)',
        shortcut,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert match is not None, "O atalho deve tratar explicitamente a falta de argumentos."
    default_block = match.group(1)
    assignments = re.findall(r'set "AUREN_TEST_ARGS=([^"]+)"', default_block, flags=re.I)
    assert assignments == ["--camada L0,L1"]
    assert "L2" not in assignments[0] and "L4" not in assignments[0] and "L5" not in assignments[0]
    assert 'set "AUREN_TEST_ARGS=%*"' in shortcut, "Argumentos explicitos devem ser preservados."
    assert '%AUREN_PYTHON% testes_auren.py %AUREN_TEST_ARGS%' in shortcut
    assert "if errorlevel 1" in shortcut, "Preflight de dependencias deve continuar."


def test_manual_tester_default_remains_l0_l1_only():
    """Atalho e runner Python nao devem divergir sobre o padrao."""
    source = (ROOT / "testes_auren_live.py").read_text(encoding="utf-8")
    assert 'requested = {"L0", "L1"}' in source
    assert 'if "--completo" in args:' in source
    assert 'requested = {"L0", "L1", "L2", "L4", "L5"}' in source


def test_l1_manual_tester_matches_ui_automation_and_mouse_confirmation_policy():
    """Evita reportar politica CONFIRM segura como falha no teste L1."""
    from core.permission_manager import PermissionManager, PermissionLevel

    manager = PermissionManager()
    normal = manager.nivel_da_acao("clicar_elemento_windows", {"alvo": "abrir"})
    sensitive = manager.nivel_da_acao("clicar_elemento_windows", {"alvo": "excluir"})
    mouse = manager.nivel_da_acao(
        "clicar_mouse_windows",
        {"x": 10, "y": 10, "botao": "esquerdo", "descricao": "botao Pesquisar"},
    )
    assert normal[0] == sensitive[0] == mouse[0] == PermissionLevel.CONFIRM
    assert "clique" in mouse[1].lower() and "confirmacao" in mouse[1].lower()

    source = (ROOT / "testes_auren_live.py").read_text(encoding="utf-8")
    assert '"clique_normal": "confirm"' in source
    assert '"clique_sensivel": "confirm"' in source
    assert '"clique" in mouse_reason.lower() and "confirmacao" in mouse_reason.lower()' in source
