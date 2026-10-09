from __future__ import annotations

import unicodedata
from queue import Empty, Queue
from typing import Any

from core.confirmation import ConfirmationRequest
from voice.input import CapturedAudio


_RESPOSTAS_AFIRMATIVAS = frozenset({
    "sim",
    "s",
    "yes",
    "y",
    "pode",
    "pode sim",
    "sim pode",
    "confirmo",
    "autorizo",
})
_PALAVRAS_DE_NEGACAO = frozenset({"nao", "nunca", "cancela", "para"})


def normalizar_resposta_falada(texto: Any) -> str:
    """Normaliza texto de ASR e comandos falados de forma conservadora."""

    bruto = unicodedata.normalize("NFKD", str(texto or "").lower())
    normalizado: list[str] = []
    for caractere in bruto:
        if unicodedata.combining(caractere):
            continue
        # Pontuação vira separador, evitando juntar palavras de respostas
        # estranhas como "s.i.m" e preservando a separação em "sim, pode".
        if unicodedata.category(caractere).startswith("P"):
            normalizado.append(" ")
        else:
            normalizado.append(caractere)
    return " ".join("".join(normalizado).split())


class VoiceConfirmationChannel:
    """Coleta confirmação por voz usando a captura compartilhada do modo voz."""

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
            # Descartar tudo que terminou antes do pedido explícito. Não limpar
            # novamente depois do TTS: o usuário pode responder durante o prompt.
            self._descartar_audio_pendente()
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

        # A fila compartilhada também transporta erros de captura. Só aceitamos
        # o envelope de áudio válido produzido pelo recorder do modo voz.
        if not isinstance(item, tuple) or len(item) != 2 or item[0] != "audio":
            return False
        audio = item[1]
        if not isinstance(audio, CapturedAudio):
            return False

        try:
            resposta = self._stt.transcrever(audio)
        except Exception:
            return False

        normalizada = normalizar_resposta_falada(resposta)
        palavras = set(normalizada.split())
        if palavras & _PALAVRAS_DE_NEGACAO:
            return False
        return normalizada in _RESPOSTAS_AFIRMATIVAS

    def _descartar_audio_pendente(self) -> None:
        while True:
            try:
                self._audio_queue.get_nowait()
            except Empty:
                return

    @staticmethod
    def _prompt(request: ConfirmationRequest) -> str:
        return (
            f"Preciso da sua confirmacao para {request.action}. "
            f"{request.reason} Diga sim ou nao."
        )
