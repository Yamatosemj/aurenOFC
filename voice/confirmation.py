from __future__ import annotations

import unicodedata
from queue import Empty, Queue
from typing import Any

from core.confirmation import ConfirmationRequest


class VoiceConfirmationChannel:
    """Coleta a confirmacao por voz usando o mesmo pipeline de captura do modo voz."""

    def __init__(
        self,
        *,
        tts: Any,
        stt: Any,
        audio_queue: Queue,
        timeout: float = 8.0,
        set_output_active: Any | None = None,
    ) -> None:
        self._tts = tts
        self._stt = stt
        self._audio_queue = audio_queue
        self._timeout = max(0.1, float(timeout))
        self._set_output_active = set_output_active

    def confirmar(self, request: ConfirmationRequest) -> bool:
        if self._set_output_active is not None:
            try:
                self._set_output_active(True)
            except Exception:
                pass

        try:
            self._tts.falar(self._prompt(request))
        except Exception:
            return False
        finally:
            if self._set_output_active is not None:
                try:
                    self._set_output_active(False)
                except Exception:
                    pass

        try:
            item = self._audio_queue.get(timeout=self._timeout)
        except Empty:
            return False

        if isinstance(item, tuple) and item:
            tipo_audio = item[0]
            audio = item[1] if len(item) > 1 else None
            if tipo_audio != "audio":
                return False
        else:
            audio = item

        if audio is None:
            return False

        try:
            resposta = self._stt.transcrever(audio)
        except Exception:
            return False

        return self._normalizar(resposta) in {"s", "sim", "y", "yes"}

    @staticmethod
    def _prompt(request: ConfirmationRequest) -> str:
        return (
            f"Preciso da sua confirmacao para {request.action}. "
            f"{request.reason} Diga sim ou nao."
        )

    @staticmethod
    def _normalizar(texto: Any) -> str:
        bruto = unicodedata.normalize("NFKD", str(texto or "").strip().lower())
        sem_acentos = "".join(
            caractere
            for caractere in bruto
            if not unicodedata.combining(caractere)
        )
        return " ".join(sem_acentos.split())
