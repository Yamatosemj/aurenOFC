"""O instalador de voz nao deve apagar modelos ja baixados.

Teste estatico em qualquer plataforma e execucao isolada do BAT apenas em
Windows, com launcher 'py.cmd' falso (sem pip real/rede/API).
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "instalar" / "INSTALAR_VOZ.bat"
PARAKEET = "parakeet-tdt-0.6b-v3-ptBR-TAGARELA-onnx-int8"


def test_voice_installer_keeps_cache_and_does_not_issue_delete_commands():
    content = INSTALLER.read_text(encoding="utf-8")
    commands = "\n".join(
        line for line in content.splitlines()
        if line.strip() and not line.strip().lower().startswith("rem ")
    )
    assert "pip install -r requirements-voice.txt" in commands
    assert "Cache ASR preservado" in commands
    assert not re.search(
        r"^\s*(?:rmdir|rd|del|erase|powershell|pwsh)\b",
        commands,
        flags=re.IGNORECASE | re.MULTILINE,
    )


@pytest.mark.skipif(os.name != "nt", reason="BAT so pode ser executado no Windows")
@pytest.mark.parametrize("pip_exit", [0, 17])
def test_voice_installer_preserves_completed_partial_and_other_caches_when_run(
    tmp_path: Path, pip_exit: int,
):
    # Copia isolada da arvore: o original e os dados do usuario nao sao tocados.
    root = tmp_path / "sandbox com espacos"
    path = root / "scripts" / "instalar" / "INSTALAR_VOZ.bat"
    path.parent.mkdir(parents=True)
    source = INSTALLER.read_text(encoding="utf-8")
    # A copia nao aguarda tecla e usa "call" para o py.cmd falso:
    # ao contrario do py.exe real, executar outro .cmd sem "call"
    # transferiria o controle e nao retornaria ao instalador.
    pip_command = "%PY% -m pip install -r requirements-voice.txt"
    assert source.count(pip_command) == 1
    fixture = source.replace("\npause\n", "\nrem pause (somente fixture)\n")
    fixture = fixture.replace(pip_command, "call " + pip_command)
    path.write_text(fixture, encoding="utf-8")
    (root / "requirements-voice.txt").write_text("# sem instalacao real\n", encoding="utf-8")

    artifacts = {
        f"data/voice/asr/{PARAKEET}/config.json": b"cache completo",
        f"data/voice/asr/{PARAKEET}/encoder-model.int8.onnx": b"arquivo local",
        "data/voice/asr/outro-modelo/partial.tmp": b"cache parcial de outro modelo",
        "data/voice/tts/kokoro/voz.onnx": b"modelo tts",
        "data/memory/keep.sqlite3": b"memoria preservada",
    }
    for relative, payload in artifacts.items():
        file = root / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(payload)

    # Simula o launcher py.exe usando py.cmd apenas na sandbox.
    # Esta fixture NUNCA inicia o pip real e registra os argumentos.
    fake_bin = root / "fake-bin"
    fake_bin.mkdir()
    fake_py = fake_bin / "py.cmd"
    fake_py.write_text(
        '@echo off\n>>"%AUREN_TEST_PY_LOG%" echo %*\nexit /b %AUREN_TEST_FAKE_EXIT%\n',
        encoding="utf-8",
    )
    log = root / "pip-invocation.txt"
    env = os.environ.copy()
    # PATH restrito ao stub para impedir fallback acidental para um py real.
    # "cmd.exe" e aberto pelo caminho absoluto de ComSpec.
    env["PATH"] = str(fake_bin)
    env["AUREN_TEST_PY_LOG"] = str(log)
    env["AUREN_TEST_FAKE_EXIT"] = str(pip_exit)

    proc = subprocess.run(
        # Passar "call" e o path separadamente evita a dupla camada de
        # aspas aplicada por subprocess.list2cmdline em caminhos com espacos.
        [os.environ.get("ComSpec", "cmd.exe"), "/d", "/c", "call", str(path)],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=20,
        check=False,
    )
    assert proc.returncode == pip_exit, proc.stdout + "\n" + proc.stderr
    assert "-3 -m pip install -r requirements-voice.txt" in log.read_text(encoding="utf-8")
    for relative, payload in artifacts.items():
        assert (root / relative).read_bytes() == payload, relative
    if pip_exit == 0:
        assert "INSTALACAO DA VOZ V3: 0" in proc.stdout
    else:
        assert "a instalacao das dependencias falhou" in proc.stdout
        assert "INSTALACAO DA VOZ V3: 0" not in proc.stdout
