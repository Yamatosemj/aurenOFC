"""Bootstrap unico de Python nos sete atalhos de uso principal.

Execucao real de CMD somente em copia temporaria com 'where.cmd' falso.
Nao invoca Python global, pip, GUI, voz, API ou camadas Live.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SELECTOR = SCRIPTS / "lib" / "SELECIONAR_PYTHON.cmd"
LAUNCHERS = [
    "iniciar/ABRIR_AUREN_GUI.bat",
    "iniciar/AUREN_CHROME.bat",
    "iniciar/AUREN_VOZ.bat",
    "instalar/INSTALAR_AUREN.bat",
    "instalar/INSTALAR_VOZ.bat",
    "testar/TESTAR_AUREN.bat",
    "testar/TESTAR_VOZ.bat",
]


@pytest.mark.parametrize("launcher", LAUNCHERS)
def test_main_shortcuts_use_shared_python_selector(launcher):
    script = (SCRIPTS / launcher).read_text(encoding="utf-8")
    assert 'call "%~dp0..\\lib\\SELECIONAR_PYTHON.cmd"' in script
    assert "if errorlevel 1" in script
    assert "%AUREN_PYTHON%" in script
    # Nao continuar executando o programa se o helper falhar.
    assert "if errorlevel 1 exit /b 1" in script or "exit /b 1" in script


def test_selector_priority_and_fail_closed_contract():
    content = SELECTOR.read_text(encoding="utf-8")
    assert content.startswith("@echo off")
    steps = [
        'if exist ".venv\\Scripts\\python.exe"',
        'if exist "..\\.venv\\Scripts\\python.exe"',
        "where py >nul 2>&1",
        "where python >nul 2>&1",
    ]
    offsets = [content.index(s) for s in steps]
    assert offsets == sorted(offsets)
    assert 'set "AUREN_PYTHON=py -3"' in content
    assert 'set "AUREN_PYTHON=python"' in content
    assert 'set "AUREN_PYTHON="' in content
    assert "exit /b 1" in content


def test_ordinary_test_shortcut_still_uses_l0_l1_and_preflight():
    script = (SCRIPTS / "testar" / "TESTAR_AUREN.bat").read_text(encoding="utf-8")
    assert 'set "AUREN_TEST_ARGS=--camada L0,L1"' in script
    assert 'set "AUREN_TEST_ARGS=%*"' in script
    assert '%AUREN_PYTHON% -c "import jsonschema, openai"' in script
    assert '%AUREN_PYTHON% testes_auren.py %AUREN_TEST_ARGS%' in script


def test_voice_installer_does_not_clear_models():
    script = (SCRIPTS / "instalar" / "INSTALAR_VOZ.bat").read_text(encoding="utf-8")
    assert "Cache ASR preservado" in script
    assert "rmdir" not in script.lower()
    assert "%AUREN_PYTHON% -m pip install -r requirements-voice.txt" in script


def test_voice_tests_preserve_failure_exit_code():
    script = (SCRIPTS / "testar" / "TESTAR_VOZ.bat").read_text(encoding="utf-8")
    assert '%AUREN_PYTHON% -m pytest tests\\test_voice.py -q' in script
    assert 'set "AUREN_EXIT_CODE=%ERRORLEVEL%"' in script
    assert "exit /b %AUREN_EXIT_CODE%" in script


@pytest.mark.skipif(os.name != "nt", reason="CMD requerido")
@pytest.mark.parametrize(
    "kind,where_py,where_python,selected",
    [
        ("local", "1", "1", ".venv\\Scripts\\python.exe"),
        ("parent", "1", "1", "..\\.venv\\Scripts\\python.exe"),
        ("py", "1", "1", "py -3"),
        ("python", "0", "1", "python"),
        ("missing", "0", "0", ""),
    ],
)
def test_selector_real_windows_cmd_with_fake_where_and_no_real_python(
    tmp_path: Path, kind: str, where_py: str, where_python: str, selected: str,
):
    root = tmp_path / "sandbox com espacos"
    lib = root / "scripts" / "lib"
    lib.mkdir(parents=True)
    (lib / SELECTOR.name).write_text(SELECTOR.read_text(encoding="utf-8"), encoding="utf-8")

    if kind in {"local", "parent"}:
        venv = root / ".venv" if kind == "local" else tmp_path / ".venv"
        bin_dir = venv / "Scripts"
        bin_dir.mkdir(parents=True)
        # Arquivo-fantasma; NAO e executado. Testa somente a precedencia.
        (bin_dir / "python.exe").write_bytes(b"nao executar")

    fake_bin = root / "fake-bin"
    fake_bin.mkdir()
    (fake_bin / "where.cmd").write_text(
        '@echo off\n'
        'if /i "%~1"=="py" exit /b %AUREN_TEST_WHERE_PY%\n'
        'if /i "%~1"=="python" exit /b %AUREN_TEST_WHERE_PYTHON%\n'
        'exit /b 1\n',
        encoding="utf-8",
    )
    runner = root / "RODAR_SELECTOR.cmd"
    runner.write_text(
        '@echo off\n'
        'cd /d "%~dp0"\n'
        'call "scripts\\lib\\SELECIONAR_PYTHON.cmd"\n'
        'set "SELECT_RC=%ERRORLEVEL%"\n'
        'echo SELECT_PY=%AUREN_PYTHON%\n'
        'echo SELECT_SOURCE=%AUREN_PYTHON_SOURCE%\n'
        'exit /b %SELECT_RC%\n',
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PATH"] = str(fake_bin)  # impede encontrar Python real em PATH
    env["AUREN_TEST_WHERE_PY"] = "0" if where_py == "1" else "1"
    env["AUREN_TEST_WHERE_PYTHON"] = "0" if where_python == "1" else "1"
    result = subprocess.run(
        [os.environ.get("ComSpec", "cmd.exe"), "/d", "/c", "call", str(runner)],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=20,
        check=False,
    )
    assert result.returncode == (1 if kind == "missing" else 0), result.stdout + result.stderr
    assert f"SELECT_PY={selected}\n".replace("\n", "") in result.stdout
    if kind == "missing":
        assert "[ERRO] Nao foi encontrado Python" in result.stdout
        assert "SELECT_SOURCE=" in result.stdout
    else:
        assert "[INFO] Interpretador Python:" in result.stdout
