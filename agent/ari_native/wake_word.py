"""Detecção textual/energética de wake-word inspirada no Ari.

Esta camada não inicializa microfone nem STT sozinha. Ela fornece o algoritmo
de decisão que pode ser conectado ao pipeline de voz do Auren sem criar um
segundo cérebro.
"""
from __future__ import annotations

import math
import re
import struct
import unicodedata

_NORMALIZE_WHITESPACE_RE = re.compile(r"\s+")
_WAKE_MIN_AUDIO_SECONDS = 0.3
_WAKE_MAX_AUDIO_SECONDS = 4.0
_SHORT_WAKE_WORD_MAX_LENGTH = 3
_SHORT_WAKE_WORD_EDIT_DISTANCE = 1
_LONG_WAKE_WORD_EDIT_DISTANCE = 2


def edit_distance(left: str, right: str, max_distance: int | None = None) -> int:
    if max_distance is not None and abs(len(left) - len(right)) > max_distance:
        return max_distance + 1
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            current.append(min(
                current[-1] + 1,
                previous[j] + 1,
                previous[j - 1] + (left_char != right_char),
            ))
        if max_distance is not None and min(current) > max_distance:
            return max_distance + 1
        previous = current
    return previous[-1]


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "").casefold()
    chars = []
    for char in normalized:
        codepoint = ord(char)
        if 0x30A1 <= codepoint <= 0x30F6 or codepoint in (0x30FD, 0x30FE):
            char = chr(codepoint - 0x60)
        category = unicodedata.category(char)
        if char.isspace() or category[0] in ("P", "Z"):
            chars.append(" ")
        elif category[0] in ("L", "N", "M"):
            chars.append(char)
    return _NORMALIZE_WHITESPACE_RE.sub(" ", "".join(chars)).strip()


def wake_word_matches(text: str, wake_word: str) -> bool:
    normalized_text = normalize_text(text).replace(" ", "")
    normalized_wake = normalize_text(wake_word).replace(" ", "")
    if not normalized_text or not normalized_wake:
        return False
    max_distance = (
        _SHORT_WAKE_WORD_EDIT_DISTANCE
        if len(normalized_wake) <= _SHORT_WAKE_WORD_MAX_LENGTH
        else _LONG_WAKE_WORD_EDIT_DISTANCE
    )
    return edit_distance(normalized_text, normalized_wake, max_distance) <= max_distance


def extract_command(text: str, wake_word: str) -> str | None:
    normalized = normalize_text(text)
    wake = normalize_text(wake_word)
    if not normalized or not wake:
        return None
    prefix = normalized[: len(wake)]
    if wake_word_matches(prefix, wake):
        command = normalized[len(prefix):].strip()
        return command or None
    parts = normalized.split()
    if len(parts) <= 1:
        return None
    if wake_word_matches(parts[0], wake):
        return " ".join(parts[1:]).strip() or None
    return None


def should_transcribe_wake_audio(audio_data, energy_threshold: float) -> bool:
    """Aplica gate de duração/energia semelhante ao Ari antes do STT."""
    sample_rate = int(getattr(audio_data, "sample_rate", 0) or 0)
    if sample_rate <= 0:
        return False
    raw_data = audio_data.get_raw_data(convert_width=2)
    if not raw_data or len(raw_data) % 2:
        return False
    frame_size = max(1, int(sample_rate * 0.02))
    energies = []
    frame_sum = 0.0
    count = 0
    for (sample,) in struct.iter_unpack("<h", raw_data):
        frame_sum += sample * sample
        count += 1
        if count == frame_size:
            energies.append(math.sqrt(frame_sum / count))
            frame_sum = 0.0
            count = 0
    if count:
        energies.append(math.sqrt(frame_sum / count))
    threshold = max(1.0, float(energy_threshold))
    active = [i for i, energy in enumerate(energies) if energy >= threshold]
    if not active:
        return False
    span = active[-1] - active[0] + 1
    seconds = span * frame_size / sample_rate
    if not _WAKE_MIN_AUDIO_SECONDS <= seconds <= _WAKE_MAX_AUDIO_SECONDS:
        return False
    active_energies = [energies[i] for i in active]
    if len(active_energies) / span < 0.15:
        return False
    mean = sum(active_energies) / len(active_energies)
    deviation = math.sqrt(sum((energy - mean) ** 2 for energy in active_energies) / len(active_energies))
    steady_frames = max(8, int(0.25 * sample_rate / frame_size))
    if len(active_energies) >= steady_frames and mean > 0 and deviation / mean < 0.12:
        return False
    return True
