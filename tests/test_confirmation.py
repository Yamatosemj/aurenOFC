from __future__ import annotations

from queue import Queue

import pytest

from core.confirmation import ConfirmationRequest, TextConfirmationChannel
from core.permission_manager import PermissionManager
from voice.confirmation import VoiceConfirmationChannel, normalizar_resposta_falada
from voice.input import CapturedAudio


_NO_ITEM = object()


def _request() -> ConfirmationRequest:
    return ConfirmationRequest(
        tool_name="encerrar_processo_windows",
        action="encerrar o processo '1234'",
        reason="Encerrar um processo pode perder trabalho.",
        actions_attempted=1,
        max_actions=10,
        actions_remaining=9,
    )


def _audio(label: str = "audio de teste") -> CapturedAudio:
    return CapturedAudio(
        samples=[0.0, 0.1],
        sample_rate=16_000,
        duration=0.1,
        rms=0.07,
        peak=0.1,
        device_name=label,
    )


class _FakeTTS:
    def __init__(
        self,
        audio_queue: Queue,
        *,
        item_durante_prompt: object = _NO_ITEM,
        exigir_fila_vazia: bool = False,
    ):
        self.audio_queue = audio_queue
        self.item_durante_prompt = item_durante_prompt
        self.exigir_fila_vazia = exigir_fila_vazia
        self.falas: list[str] = []

    def falar(self, texto: str) -> None:
        self.falas.append(texto)
        if self.exigir_fila_vazia:
            assert self.audio_queue.empty(), "a fila antiga deveria ser limpa antes do prompt"
        if self.item_durante_prompt is not _NO_ITEM:
            self.audio_queue.put(self.item_durante_prompt)


class _FakeSTT:
    def __init__(self, resposta: str):
        self.resposta = resposta
        self.recebidos: list[object] = []

    def transcrever(self, audio: object) -> str:
        self.recebidos.append(audio)
        return self.resposta


def _voice_channel(
    *,
    resposta: str = "sim",
    queue_item_durante_prompt: object = _NO_ITEM,
    exigir_fila_vazia: bool = False,
    audio_queue: Queue | None = None,
    stt: object | None = None,
    timeout: float = 0.1,
):
    queue = audio_queue or Queue()
    tts = _FakeTTS(
        queue,
        item_durante_prompt=queue_item_durante_prompt,
        exigir_fila_vazia=exigir_fila_vazia,
    )
    transcriber = stt or _FakeSTT(resposta)
    channel = VoiceConfirmationChannel(
        tts=tts,
        stt=transcriber,
        audio_queue=queue,
        timeout=timeout,
    )
    return channel, tts, transcriber, queue


def test_text_confirmation_channel_preserves_interactive_behavior():
    prompts = []
    channel = TextConfirmationChannel(
        input_fn=lambda prompt: (prompts.append(prompt) or "s"),
    )

    assert channel.confirmar(_request()) is True
    assert prompts == ["Autorizar? [s/n]: "]


def test_permission_manager_delegates_confirmation_to_injected_channel(monkeypatch):
    captured = []

    class FakeChannel:
        def confirmar(self, request):
            captured.append(request)
            return True

    def fail_input(*_args, **_kwargs):
        raise AssertionError("PermissionManager nao deve ler stdin diretamente.")

    monkeypatch.setattr("builtins.input", fail_input)

    pm = PermissionManager(confirmation_channel=FakeChannel())
    permitido, motivo = pm.autorizar(
        "encerrar_processo_windows",
        {"pid": 4321, "nome": ""},
    )

    assert permitido is True
    assert motivo == "Usuario confirmou a acao."
    assert len(captured) == 1
    assert captured[0].tool_name == "encerrar_processo_windows"
    assert captured[0].actions_attempted == 1


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Sim.", "sim"),
        ("Sim!", "sim"),
        ("  SÍM,   pode. ", "sim pode"),
        ("Fechar o Auren.", "fechar o auren"),
        ("não", "nao"),
        ("s.i.m", "s i m"),
    ],
)
def test_normalizar_resposta_falada_removes_accents_punctuation_and_extra_spaces(raw, expected):
    assert normalizar_resposta_falada(raw) == expected


@pytest.mark.parametrize(
    "resposta",
    [
        "Sim.",
        "Sim!",
        "sim, pode",
        "s",
        "yes",
        "y",
        "pode",
        "pode sim",
        "sim pode",
        "confirmo",
        "autorizo",
    ],
)
def test_voice_confirmation_accepts_only_explicit_affirmative_responses(resposta):
    fresh_audio = _audio("resposta nova")
    channel, tts, stt, queue = _voice_channel(
        resposta=resposta,
        queue_item_durante_prompt=("audio", fresh_audio),
    )

    assert channel.confirmar(_request()) is True
    assert tts.falas and "Diga sim ou nao." in tts.falas[0]
    assert stt.recebidos == [fresh_audio]
    assert queue.empty()


@pytest.mark.parametrize(
    "resposta",
    ["Sim, não", "não", "cancela", "talvez", "nunca", "para", "sim, para"],
)
def test_voice_confirmation_denies_negations_and_unclear_responses(resposta):
    fresh_audio = _audio("resposta ambigua")
    channel, _, stt, _ = _voice_channel(
        resposta=resposta,
        queue_item_durante_prompt=("audio", fresh_audio),
    )

    assert channel.confirmar(_request()) is False
    assert stt.recebidos == [fresh_audio]


def test_voice_confirmation_discards_old_audio_before_prompt_and_uses_new_speech():
    old_audio = _audio("resposta antiga")
    fresh_audio = _audio("resposta durante o prompt")
    queue = Queue()
    queue.put(("audio", old_audio))
    channel, tts, stt, _ = _voice_channel(
        queue_item_durante_prompt=("audio", fresh_audio),
        exigir_fila_vazia=True,
        audio_queue=queue,
    )

    assert channel.confirmar(_request()) is True
    assert tts.falas
    assert stt.recebidos == [fresh_audio]
    assert old_audio not in stt.recebidos


def test_voice_confirmation_does_not_approve_from_old_audio_without_new_speech():
    old_audio = _audio("resposta antiga")
    queue = Queue()
    queue.put(("audio", old_audio))

    class UnexpectedSTT:
        def transcrever(self, _audio):
            raise AssertionError("áudio antigo não deve chegar ao ASR")

    channel, _, stt, _ = _voice_channel(
        audio_queue=queue,
        stt=UnexpectedSTT(),
    )

    assert channel.confirmar(_request()) is False


@pytest.mark.parametrize(
    "queue_item",
    [
        ("erro_captura", RuntimeError("microfone indisponivel")),
        ("audio", None),
        ("audio", "texto nao e payload de audio"),
        ("outro_tipo", _audio()),
        _audio(),
        None,
    ],
)
def test_voice_confirmation_denies_invalid_queue_items(queue_item):
    channel, _, stt, _ = _voice_channel(queue_item_durante_prompt=queue_item)

    assert channel.confirmar(_request()) is False
    assert stt.recebidos == []


def test_voice_confirmation_denies_on_timeout():
    channel, _, stt, _ = _voice_channel()

    assert channel.confirmar(_request()) is False
    assert stt.recebidos == []


@pytest.mark.parametrize(
    "mensagem",
    ["Sair.", "Encerrar.", "Fechar o Auren."],
)
def test_voice_main_exit_commands_accept_punctuation(mensagem):
    from voice.main import _eh_comando_saida

    assert _eh_comando_saida(mensagem) is True


@pytest.mark.parametrize("mensagem", ["sair agora", "não sair", "fechar o Auren depois"])
def test_voice_main_exit_commands_still_require_exact_command(mensagem):
    from voice.main import _eh_comando_saida

    assert _eh_comando_saida(mensagem) is False
