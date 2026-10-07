from __future__ import annotations

import secrets
import time
import unicodedata
from queue import Empty, Queue
from typing import Any, Callable

from core.confirmation import (
    TIMEOUT_SECONDS,
    ConfirmationGate,
    ConfirmationRequest,
)
from voice.input import CapturedAudio


class VoiceConfirmationChannel:
    """Coleta confirmacao por voz usando o protocolo real da fila de voz."""

    _AFFIRMATIVE_RESPONSES = frozenset({
        "s",
        "sim",
        "y",
        "yes",
        "sim pode",
        "pode sim",
    })

    def __init__(
        self,
        *,
        tts: Any,
        stt: Any,
        audio_queue: Queue,
        timeout: float = TIMEOUT_SECONDS,
        gate: ConfirmationGate | None = None,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        self._tts = tts
        self._stt = stt
        self._audio_queue = audio_queue
        if gate is None:
            from core.confirmation import DEFAULT_CONFIRMATION_GATE
            self._gate = DEFAULT_CONFIRMATION_GATE
        else:
            self._gate = gate
        self._token_factory = token_factory or self._novo_token

    @staticmethod
    def _novo_token() -> str:
        """Gera o nonce opaco exclusivamente na interface de voz.
        O token fica fora do contrato da tool e nunca e criado pelo modelo.
        Custo: O(1) para gerar um nonce criptograficamente forte.
        """
        return secrets.token_urlsafe(32)

    def confirmar(self, request: ConfirmationRequest) -> bool:
        token = self._token_factory()
        if not self._gate.abrir(token):
            return False

        try:
            # Descarta tudo que chegou antes do inicio desta janela de confirmacao.
            self._drenar_fila_pendente()
            janela_inicio = time.perf_counter()

            try:
                self._tts.falar(self._prompt(request))
            except Exception:
                return False

            while True:
                restante = self._gate.restante(token)
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

                if audio.captured_at < janela_inicio:
                    continue

                try:
                    resposta = self._stt.transcrever(audio)
                except Exception:
                    return False

                aprovado = self._normalizar(resposta) in self._AFFIRMATIVE_RESPONSES
                return self._gate.resolver(token, aprovado)
        finally:
            self._gate.cancelar(token)

    def _drenar_fila_pendente(self) -> None:
        while True:
            try:
                self._audio_queue.get_nowait()
            except Empty:
                return

    @staticmethod
    def _extrair_audio(item: Any) -> CapturedAudio | None:
        """Extrai somente audio capturado pelo produtor oficial da fila.
        Itens antigos, erros e formatos legados sao descartados antes do ASR.
        Custo: O(1).
        """
        if not isinstance(item, tuple) or len(item) != 2:
            return None

        tipo, payload = item
        if tipo != "audio" or not isinstance(payload, CapturedAudio):
            return None

        return payload

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
