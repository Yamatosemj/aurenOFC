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
    "iniciar/AUREN_DESKTOP.bat": "desktop\\electron\\main.cjs",
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
