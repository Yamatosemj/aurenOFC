from __future__ import annotations

import json
import os
from types import SimpleNamespace

from core.capability_audio_runtime import ENV_FLAG, try_execute
from core.tool_result import ToolResult


def test_flag_disabled_does_not_resolve(monkeypatch):
    monkeypatch.delenv(ENV_FLAG, raising=False)
    called = []

    ok, message, metadata = try_execute(
        "volume 40%",
        executar_ferramenta=lambda item: called.append(item) or ToolResult.success("ok"),
    )

    assert ok is False
    assert message == ""
    assert called == []
    assert metadata["reason"] == "flag_disabled"


def test_audio_experiment_executes_local_volume(monkeypatch):
    monkeypatch.setenv(ENV_FLAG, "1")
    calls = []

    def execute(item):
        calls.append(item)
        return ToolResult.success("Volume definido para 40%.", tool_name=item.name)

    ok, message, metadata = try_execute("volume 40%", executar_ferramenta=execute)

    assert ok is True
    assert message == "Volume definido para 40%."
    assert metadata["tool"] == "definir_volume_windows"
    assert metadata["tool_ok"] is True
    assert len(calls) == 1
    assert calls[0].name == "definir_volume_windows"
    assert json.loads(calls[0].arguments) == {"percentual": 40}


def test_audio_experiment_executes_local_media(monkeypatch):
    monkeypatch.setenv(ENV_FLAG, "1")
    calls = []

    def execute(item):
        calls.append(item)
        return ToolResult.success("Comando de midia enviado: proxima.", tool_name=item.name)

    ok, _, metadata = try_execute("próxima música", executar_ferramenta=execute)

    assert ok is True
    assert metadata["tool"] == "controle_midia_windows"
    assert json.loads(calls[0].arguments) == {"acao": "proxima"}


def test_audio_experiment_falls_back_when_not_audio(monkeypatch):
    monkeypatch.setenv(ENV_FLAG, "1")
    called = []

    ok, message, metadata = try_execute(
        "abra o YouTube",
        executar_ferramenta=lambda item: called.append(item) or ToolResult.success("ok"),
    )

    assert ok is False
    assert message == ""
    assert called == []
    assert metadata["reason"] == "not_resolved_audio_local"


def test_audio_runtime_does_not_capture_music_search(monkeypatch):
    monkeypatch.setenv(ENV_FLAG, "1")
    called = []

    ok, message, metadata = try_execute(
        "pesquise a música Evidências",
        executar_ferramenta=lambda item: called.append(item) or ToolResult.success("ok"),
    )

    assert ok is False
    assert message == ""
    assert called == []
    assert metadata["reason"] == "not_resolved_audio_local"
