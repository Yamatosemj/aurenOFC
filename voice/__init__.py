"""Voice Engine V3 local-first do Auren."""

from .audio_devices import (
    carregar_escolha,
    estado_dispositivos,
    listar_dispositivos,
    prefetch,
    resolver_dispositivo,
    salvar_escolha,
)
from .input import AudioCapture, AudioCaptureConfig, CapturedAudio, PushToTalkRecorder
from .stt import LocalPortugueseASR
from .tts import LocalKokoroTTS
from .speech_response import SpeechResponseFormatter

__all__ = [
    "AudioCapture",
    "AudioCaptureConfig",
    "CapturedAudio",
    "PushToTalkRecorder",
    "LocalPortugueseASR",
    "LocalKokoroTTS",
    "SpeechResponseFormatter",
    "carregar_escolha",
    "estado_dispositivos",
    "listar_dispositivos",
    "prefetch",
    "resolver_dispositivo",
    "salvar_escolha",
]
