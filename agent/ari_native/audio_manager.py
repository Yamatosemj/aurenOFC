"""Gerenciador de recursos de áudio inspirado no Ari.

Adaptado para o backend `sounddevice` já usado pelo Auren: entrada e saída têm
locks separados para evitar que captura e TTS concorram pelo mesmo backend.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager

_audio_input_lock = threading.Lock()
_audio_output_lock = threading.Lock()


def get_audio_input_lock() -> threading.Lock:
    return _audio_input_lock


def get_audio_output_lock() -> threading.Lock:
    return _audio_output_lock


@contextmanager
def input_session():
    with _audio_input_lock:
        yield


@contextmanager
def output_session():
    with _audio_output_lock:
        yield
