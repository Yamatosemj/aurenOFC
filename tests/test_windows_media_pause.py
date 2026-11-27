"""Pausa GSMTC com sessoes sinteticas; nunca consulta o Windows real."""

from __future__ import annotations

import asyncio
import json
import sys
from types import SimpleNamespace

import pytest

from core.permission_manager import PermissionLevel, PermissionManager
from core.local_decision import LocalDecisionEngine
from core.tool_contracts import validate_tool_arguments
from core.tool_result import ToolResult
from tools import windows_input, windows_media
from tools.dispatcher import executar_ferramenta


class FakeSession:
    def __init__(self, *states, pause_enabled=True, accepted=True, app_id="Player.Sintetico"):
        self.states = list(states)
        self.pause_enabled = pause_enabled
        self.accepted = accepted
        self.source_app_user_model_id = app_id
        self.pause_calls = 0

    def get_playback_info(self):
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        if isinstance(state, Exception):
            raise state
        return SimpleNamespace(
            playback_status=state,
            controls=SimpleNamespace(is_pause_enabled=self.pause_enabled),
        )

    async def try_pause_async(self):
        self.pause_calls += 1
        if isinstance(self.accepted, Exception):
            raise self.accepted
        return self.accepted


class FakeManager:
    def __init__(self, *sessions):
        self.sessions = sessions

    def get_sessions(self):
        return self.sessions


def pause(*sessions):
    return asyncio.run(windows_media._pause_with_manager(FakeManager(*sessions)))


def test_confirmed_pause_reads_before_and_after_on_same_session():
    target = FakeSession(4, 4, 4, 5)
    other = FakeSession(5)
    result = pause(target, other)

    assert result.ok is True
    assert result.data == {
        "estado": "pausa_confirmada", "antes": "reproduzindo", "depois": "pausada",
        "comando_enviado": True, "aplicativo": "Player.Sintetico",
    }
    assert target.pause_calls == 1
    assert other.pause_calls == 0


@pytest.mark.parametrize("sessions,code", [
    ((), "media_session_absent"),
    ((FakeSession(3),), "media_not_playing"),
    ((FakeSession(4), FakeSession(4)), "media_session_ambiguous"),
    ((FakeSession(5), FakeSession(5)), "media_session_ambiguous"),
])
def test_absent_nonplaying_or_ambiguous_sessions_do_not_pause(sessions, code):
    result = pause(*sessions)
    assert result.ok is False
    assert result.error_code == code
    assert result.data["estado"] == "falha"
    assert all(session.pause_calls == 0 for session in sessions)


def test_already_paused_never_resumes():
    target = FakeSession(5)
    result = pause(target)
    assert result.ok is True
    assert result.data["estado"] == "ja_pausada"
    assert result.data["comando_enviado"] is False
    assert target.pause_calls == 0


def test_state_changes_to_paused_before_command():
    target = FakeSession(4, 5)
    result = pause(target)
    assert result.ok is True
    assert result.data["estado"] == "ja_pausada"
    assert target.pause_calls == 0


def test_changing_session_prevents_unsafe_selection():
    target = FakeSession(4)
    result = pause(target, FakeSession(2))
    assert result.error_code == "media_state_unknown"
    assert result.data["estado"] == "desconhecido"
    assert target.pause_calls == 0


def test_unreadable_state_before_command_prevents_pause():
    target = FakeSession(4, RuntimeError("leitura falhou"))
    result = pause(target)
    assert result.error_code == "media_state_unknown"
    assert result.data["comando_enviado"] is False
    assert target.pause_calls == 0


def test_pause_unsupported_and_rejected_are_failures():
    unsupported = FakeSession(4, 4, pause_enabled=False)
    rejected = FakeSession(4, 4, accepted=False)
    assert pause(unsupported).error_code == "media_pause_unavailable"
    assert pause(rejected).error_code == "media_pause_rejected"
    assert unsupported.pause_calls == 0
    assert rejected.pause_calls == 1


def test_rejected_request_with_changed_state_is_unknown():
    target = FakeSession(4, 4, 5, accepted=False)
    result = pause(target)
    assert result.error_code == "media_state_unknown"
    assert result.data["depois"] == "pausada"
    assert target.pause_calls == 1


def test_post_request_without_paused_state_is_unknown(monkeypatch):
    monkeypatch.setattr(windows_media, "_VERIFY_TIMEOUT_SECONDS", 0)
    target = FakeSession(4)
    result = pause(target)
    assert result.ok is False
    assert result.error_code == "media_state_unknown"
    assert result.data["comando_enviado"] is True
    assert result.data["depois"] == "reproduzindo"
    assert target.pause_calls == 1


@pytest.mark.parametrize("target", [
    FakeSession(4, 4, RuntimeError("leitura falhou")),
    FakeSession(4, 4, accepted=RuntimeError("requisicao falhou")),
])
def test_failures_after_pause_attempt_are_unknown(target):
    result = pause(target)
    assert result.error_code == "media_state_unknown"
    assert result.data["comando_enviado"] is True
    assert target.pause_calls == 1


def test_linux_path_is_safe_and_does_not_load_backend(monkeypatch):
    monkeypatch.setattr(windows_media, "_is_windows", lambda: False)
    monkeypatch.setattr(windows_media, "_pause", lambda: pytest.fail("backend iniciado"))
    result = windows_media.pausar_midia_windows()
    assert result.error_code == "media_platform_unsupported"


def test_running_event_loop_fails_without_starting_backend(monkeypatch):
    monkeypatch.setattr(windows_media, "_is_windows", lambda: True)
    monkeypatch.setattr(windows_media, "_pause", lambda: pytest.fail("backend iniciado"))

    async def call():
        return windows_media.pausar_midia_windows()

    result = asyncio.run(call())
    assert result.error_code == "media_state_unknown"
    assert result.data["comando_enviado"] is False


@pytest.mark.skipif(sys.platform != "win32", reason="PyWinRT e exclusivo do Windows")
def test_pywinrt_import_contract_without_accessing_real_sessions():
    control = pytest.importorskip("winrt.windows.media.control")
    media = pytest.importorskip("winrt.windows.media")
    manager = control.GlobalSystemMediaTransportControlsSessionManager
    session = control.GlobalSystemMediaTransportControlsSession
    status = control.GlobalSystemMediaTransportControlsSessionPlaybackStatus
    assert callable(manager.request_async)
    assert callable(session.get_playback_info)
    assert callable(session.try_pause_async)
    assert status.PLAYING == 4 and status.PAUSED == 5
    assert media.MediaPlaybackType is not None


def test_local_pause_intent_maps_to_explicit_action():
    for phrase in ("pausa", "pause", "pausar"):
        decision = LocalDecisionEngine().choice(phrase)
        assert decision.choice == "control_media"
        assert decision.arguments == {"acao": "pausar"}


def test_pause_route_never_uses_global_toggle(monkeypatch):
    failure = ToolResult.failure("estado desconhecido", error_code="media_state_unknown")
    monkeypatch.setattr(windows_media, "pausar_midia_windows", lambda: failure)
    monkeypatch.setattr(windows_input, "_pressionar_vk", lambda *a, **k: pytest.fail("tecla global acionada"))
    assert windows_input.controle_midia_windows("pausar") is failure


def test_contract_and_permission_guard_run_before_executor(monkeypatch):
    assert validate_tool_arguments("controle_midia_windows", {"acao": "pausar"})[0]
    assert not validate_tool_arguments("controle_midia_windows", {"acao": "pausar", "extra": 1})[0]
    calls = []
    monkeypatch.setattr(windows_media, "pausar_midia_windows", lambda: calls.append(1) or ToolResult.success("Pausa confirmada.", data={"estado": "pausa_confirmada"}))
    item = SimpleNamespace(name="controle_midia_windows", arguments=json.dumps({"acao": "pausar"}))

    denied = PermissionManager()
    denied.policy["windows.audio.control"] = PermissionLevel.BLOCKED
    result = executar_ferramenta(item, denied, None)
    assert result.ok is False
    assert result.error_code == "permission_denied"
    assert calls == []

    allowed = PermissionManager()
    result = executar_ferramenta(item, allowed, None)
    assert result.ok is True
    assert result.data["estado"] == "pausa_confirmada"
    assert calls == [1]

    after_external_content = PermissionManager()
    after_external_content.registrar_fonte_nao_confiavel("ler_pagina")
    assert after_external_content.nivel_da_acao("controle_midia_windows", {"acao": "pausar"})[0] is PermissionLevel.CONFIRM


def test_global_toggle_is_blocked_after_pause_attempt_in_same_task(monkeypatch):
    calls = []
    monkeypatch.setattr(windows_media, "pausar_midia_windows", lambda: ToolResult.failure("nao confirmado", error_code="media_state_unknown"))
    monkeypatch.setattr(windows_input, "_pressionar_vk", lambda *a, **k: calls.append(1))
    manager = PermissionManager()
    pause_item = SimpleNamespace(name="controle_midia_windows", arguments='{"acao":"pausar"}')
    toggle_item = SimpleNamespace(name="controle_midia_windows", arguments='{"acao":"play_pause"}')

    assert executar_ferramenta(pause_item, manager, None).error_code == "media_state_unknown"
    blocked = executar_ferramenta(toggle_item, manager, None)
    assert blocked.error_code == "permission_denied"
    assert calls == []

    restored = PermissionManager()
    restored.restore_limits(manager.checkpoint_limits())
    assert restored.nivel_da_acao("controle_midia_windows", {"acao": "play_pause"})[0] is PermissionLevel.BLOCKED
    restored.iniciar_tarefa()
    assert restored.nivel_da_acao("controle_midia_windows", {"acao": "play_pause"})[0] is PermissionLevel.AUTO

    legacy_checkpoint = manager.checkpoint_limits()
    del legacy_checkpoint["_pausa_midia_na_tarefa"]
    restored.restore_limits(legacy_checkpoint)
    assert restored.nivel_da_acao("controle_midia_windows", {"acao": "play_pause"})[0] is PermissionLevel.AUTO
