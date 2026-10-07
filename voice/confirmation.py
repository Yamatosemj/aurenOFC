from __future__ import annotations

import time
import unicodedata
from queue import Empty, Queue
from typing import Any

from core.confirmation import ConfirmationRequest
from voice.input import CapturedAudio


class VoiceConfirmationChannel:
    """Coleta a confirmacao por voz usando o mesmo pipeline de captura do modo voz."""

    def __init__(
        self,
        *,
        tts: Any,
        stt: Any,
        audio_queue: Queue,
        timeout: float = 8.0,
    ) -> None:
        self._tts = tts
        self._stt = stt
        self._audio_queue = audio_queue
        self._timeout = max(0.1, float(timeout))

    def confirmar(self, request: ConfirmationRequest) -> bool:
        self._drenar_fila_pendente()

        try:
            self._tts.falar(self._prompt(request))
        except Exception:
            return False

        pronto_em = time.perf_counter()
        limite = pronto_em + self._timeout
        while True:
            restante = limite - time.perf_counter()
            if restante <= 0:
                return False

            try:
                item = self._audio_queue.get(timeout=restante)
            except Empty:
                return False

            if isinstance(item, tuple) and len(item) == 2 and item[0] == "erro":
                return False

            audio = self._extrair_audio(item)
            if audio is None:
                continue

            if audio.captured_at < pronto_em:
                continue

            try:
                resposta = self._stt.transcrever(audio)
            except Exception:
                return False

            return self._normalizar(resposta) in self._AFFIRMATIVE_RESPONSES

    def _drenar_fila_pendente(self) -> None:
        while True:
            try:
                self._audio_queue.get_nowait()
            except Empty:
                return
    @staticmethod,    def _extrair_audio(item: Any) -> CapturedAudio | None:,        """Extrai somente audio capturado pelo protocolo real da fila.""",        if not isinstance(item, tuple) or len(item) != 2:,            return None,,        tipo, payload = item,        if tipo != "audio" or not isinstance(payload, CapturedAudio):,            return None,,        return payload,    _AFFIRMATIVE_RESPONSES = frozenset({"s", "sim", "y", "yes", "sim pode", "pode sim"})

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
        sem_pontuacao = "".join(
            " " if unicodedata.category(caractere).startswith("P") else caractere
            for caractere in sem_acentos
        )
        return " ".join(sem_pontuacao.split())
