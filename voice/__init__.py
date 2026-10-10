"""Voice Engine V4 local-first do Auren."""

from .input import AudioCapture, AudioCaptureConfig, CapturedAudio, PushToTalkRecorder
from .segmentation import VoiceActivitySegmenter, VoiceSegment, VoiceSegmentConfig
from .stt import LocalPortugueseASR
from .tts import LocalKokoroTTS
from .speech_response import SpeechResponseFormatter

__all__ = [
    "AudioCapture",
    "AudioCaptureConfig",
    "CapturedAudio",
    "PushToTalkRecorder",
    "VoiceActivitySegmenter",
    "VoiceSegment",
    "VoiceSegmentConfig",
    "LocalPortugueseASR",
    "LocalKokoroTTS",
    "SpeechResponseFormatter",
]
