"""Regressoes da revisao da pausa GSMTC, com modelo e efeito simulados."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.harness import AurenHarness
from core.capability_audio_runtime import make_task_spec
from core.capability_resolver import CapabilityResolver
from core.intent_resolver import _extract_audio_action
from core.intent_verification import IntentDecision
from core.permission_manager import PermissionManager
from core.tool_result import ToolResult
from tools import windows_media
from tools.dispatcher import executar_ferramenta


def test_explicit_play_pause_stays_a_toggle():
    for phrase in ("play/pause", "alternar play/pause", "alterna play pause"):
        assert _extract_audio_action(phrase)[0] == "play_pause"
    assert _extract_audio_action("pausa a música")[0] == "pausar"
    assert _extract_audio_action("próxima música")[0] == "proxima"
    assert _extract_audio_action("música anterior")[0] == "anterior"
    resolution = CapabilityResolver().resolve(make_task_spec("alternar play/pause"))
    assert resolution.status == "resolved"
    assert resolution.params["acao"] == "play_pause"


def test_normal_harness_does_not_repeat_unknown_pause(monkeypatch):
    effects = []

    def unknown_pause():
        effects.append("pausa_tentada")
        return ToolResult.failure(
            "A pausa foi solicitada, mas o estado final e desconhecido.",
            error_code="media_state_unknown",
            data={"estado": "desconhecido", "comando_enviado": True},
        )

    monkeypatch.setattr(windows_media, "pausar_midia_windows", unknown_pause)
    manager = PermissionManager()

    def call(call_id):
        return SimpleNamespace(
            type="function_call", name="controle_midia_windows",
            arguments='{"acao":"pausar"}', call_id=call_id,
        )

    responses = iter((
        SimpleNamespace(output=[call("primeira")], output_text="", usage=None),
        SimpleNamespace(output=[call("segunda")], output_text="", usage=None),
        SimpleNamespace(output=[], output_text="Nao consegui confirmar a pausa.", usage=None),
    ))
    harness = AurenHarness(
        criar_resposta=lambda *_args, **_kwargs: next(responses),
        executar_ferramenta=lambda item: executar_ferramenta(item, manager, None),
        mostrar_uso=lambda: None,
        obter_chamadas=lambda response: [item for item in response.output if item.type == "function_call"],
        comando_rapido=lambda _message: (False, ""),
        iniciar_tarefa=manager.iniciar_tarefa,
        apos_tarefa=None,
        fechar=lambda: None,
        verificar_intencao=lambda *_args: IntentDecision("aprovar", "frase sintetica"),
        permission_manager=manager,
        max_model_rounds=3,
    )

    harness.processar_mensagem("pausa a música")
    assert effects == ["pausa_tentada"]
    assert manager.nivel_da_acao("controle_midia_windows", {"acao": "pausar"})[0].value == "blocked"
    for action in ("proxima", "anterior", "parar"):
        assert manager.nivel_da_acao("controle_midia_windows", {"acao": action})[0].value == "auto"

    resumed = PermissionManager()
    resumed.restore_limits(manager.checkpoint_limits())
    assert resumed.nivel_da_acao("controle_midia_windows", {"acao": "pausar"})[0].value == "blocked"
    resumed.iniciar_tarefa()
    assert resumed.nivel_da_acao("controle_midia_windows", {"acao": "pausar"})[0].value == "auto"


@pytest.mark.parametrize("error_code,data", [
    ("media_session_absent", {"estado": "falha"}),
    ("media_state_unknown", {"estado": "desconhecido", "comando_enviado": False}),
])
def test_retry_remains_possible_when_no_pause_was_sent(monkeypatch, error_code, data):
    effects = []
    monkeypatch.setattr(
        windows_media, "pausar_midia_windows",
        lambda: effects.append(1) or ToolResult.failure("Sem efeito.", error_code=error_code, data=data),
    )
    manager = PermissionManager()
    item = SimpleNamespace(name="controle_midia_windows", arguments='{"acao":"pausar"}')

    assert executar_ferramenta(item, manager, None).error_code == error_code
    assert executar_ferramenta(item, manager, None).error_code == error_code
    assert effects == [1, 1]


def test_executor_exception_is_treated_as_uncertain_effect(monkeypatch):
    effects = []

    def raise_after_attempt():
        effects.append(1)
        raise RuntimeError("falha sintetica apos a tentativa")

    monkeypatch.setattr(windows_media, "pausar_midia_windows", raise_after_attempt)
    manager = PermissionManager()
    item = SimpleNamespace(name="controle_midia_windows", arguments='{"acao":"pausar"}')

    first = executar_ferramenta(item, manager, None)
    second = executar_ferramenta(item, manager, None)
    assert first.error_code == "media_state_unknown"
    assert second.error_code == "permission_denied"
    assert effects == [1]
