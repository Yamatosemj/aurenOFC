"""Escada local de modelos com timeout e cooldown por classe de falha.

WHY THIS EXISTS
    Um provider nao deve pagar novamente o tempo de um modelo que acabou de
    provar que nao consegue responder. A escada tenta o primeiro modelo
    configurado, descarta degraus com falhas transitorias por um periodo
    limitado e continua sem criar um segundo caminho de execucao.

COMO FUNCIONA
    Os modelos chegam da configuracao e sao tentados da esquerda para a direita.
    429 esfria por 5 minutos, 503/504 e timeouts por 30 minutos e 404 por 6 horas.
    400/401 e outras falhas nao trocam de modelo.

CUSTO
    Memoria O(N) para os cooldowns, onde N e o numero de modelos configurados.
    Cada tentativa faz no maximo uma chamada ao cliente; o modulo nao faz sleep.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Callable, Mapping


COOLDOWN_QUOTA_SECONDS = 5 * 60
COOLDOWN_UNAVAILABLE_SECONDS = 30 * 60
COOLDOWN_GONE_SECONDS = 6 * 60 * 60


class ModelLadderError(RuntimeError):
    """Erro estruturado produzido pela escada de modelos.

    Guarda um codigo estavel e dados auxiliares para logs/testes.
    Nao altera o fluxo de ferramentas nem cria execucao paralela.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str,
        data: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.data = dict(data or {})

    def as_dict(self) -> dict[str, Any]:
        """Retorna a falha em formato estruturado e estavel.

        O chamador pode registrar codigo, modelos e cooldowns sem parsear texto.
        O custo e O(1) para a estrutura ja armazenada.
        """
        return {
            "ok": False,
            "codigo_erro": self.code,
            "mensagem": str(self),
            "dados": dict(self.data),
        }


class ModelLadderExhaustedError(ModelLadderError):
    """Indica que nenhum degrau da escada pode ser usado agora.

    O erro informa os modelos e o tempo restante de cada cooldown para diagnostico.
    Nao executa nova tentativa automatica depois de ser criado.
    """

    def __init__(
        self,
        models: tuple[str, ...],
        remaining: Mapping[str, float],
        *,
        last_error: Exception | None = None,
    ) -> None:
        detail = ", ".join(
            f"{model} ({max(0.0, float(seconds)):.0f}s)"
            for model, seconds in remaining.items()
        )
        message = "Todos os modelos da escada estao em cooldown"
        if detail:
            message += f": {detail}."
        else:
            message += "."
        if last_error is not None:
            message += f" Ultima falha: {last_error}"
        super().__init__(
            message,
            code="model_ladder_exhausted",
            data={
                "modelos": list(models),
                "cooldowns_restantes_s": {
                    model: max(0.0, float(seconds))
                    for model, seconds in remaining.items()
                },
                "ultima_falha": str(last_error) if last_error is not None else None,
            },
        )
        self.models = models
        self.last_error = last_error


class ModelLadderHistoryRequiredError(ModelLadderError):
    """Indica que uma troca de modelo exigiria historico completo.

    A API nao garante portabilidade documentada de previous_response_id entre modelos.
    O provider falha explicitamente para nunca trocar de modelo e perder contexto.
    """

    def __init__(self, model: str) -> None:
        super().__init__(
            (
                f"A troca para o modelo {model} exige historico_completo porque "
                "previous_response_id nao tem garantia documentada de portabilidade entre modelos."
            ),
            code="model_ladder_history_required",
            data={"modelo_destino": model},
        )
        self.model = model


def _status_code(error: BaseException | str) -> int | None:
    if isinstance(error, str):
        return None
    value = getattr(error, "status_code", None)
    if value is None:
        response = getattr(error, "response", None)
        value = getattr(response, "status_code", None) if response is not None else None
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _texto_erro(error: BaseException | str) -> str:
    return error if isinstance(error, str) else str(error)


def _tem_codigo(texto: str, codigo: int) -> bool:
    return re.search(rf"(?<!\d){codigo}(?!\d)", texto) is not None


def is_quota_error(error: BaseException | str) -> bool:
    """Identifica esgotamento de quota/rate limit do provider.

    Usa status_code quando o SDK oferece esse dado e marcadores textuais como fallback.
    O custo e O(len(mensagem)) no pior caso, sem chamadas de rede.
    """
    return _status_code(error) == 429 or _tem_codigo(_texto_erro(error), 429)


def is_unavailable_error(error: BaseException | str) -> bool:
    """Identifica indisponibilidade transitoria ou timeout do provider.

    Trata 503/504 e timeouts como uma classe para evitar repetir o mesmo degrau.
    O custo e O(len(mensagem)) no pior caso, sem efeitos colaterais.
    """
    status = _status_code(error)
    if status in {503, 504}:
        return True
    nome = type(error).__name__ if not isinstance(error, str) else ""
    texto = _texto_erro(error).lower()
    return (
        nome in {"APITimeoutError", "TimeoutError"}
        or "deadline_exceeded" in texto
        or "request timed out" in texto
        or "timed out" in texto
        or "service unavailable" in texto
        or _tem_codigo(texto, 503)
        or _tem_codigo(texto, 504)
    )


def is_gone_error(error: BaseException | str) -> bool:
    """Identifica um modelo removido ou inexistente.

    Usa 404/not found e deliberadamente nao transforma 403 em cooldown.
    O custo e O(len(mensagem)) no pior caso, sem I/O.
    """
    return (
        _status_code(error) == 404
        or _tem_codigo(_texto_erro(error), 404)
        or "not found" in _texto_erro(error).lower()
    )


def _politica_de_falha(error: BaseException) -> tuple[str, int] | None:
    if is_quota_error(error):
        return "quota", COOLDOWN_QUOTA_SECONDS
    if is_unavailable_error(error):
        return "unavailable", COOLDOWN_UNAVAILABLE_SECONDS
    if is_gone_error(error):
        return "gone", COOLDOWN_GONE_SECONDS
    return None


def _formatar_duracao(seconds: int) -> str:
    if seconds % 3600 == 0:
        return f"{seconds // 3600} h"
    if seconds % 60 == 0:
        return f"{seconds // 60} min"
    return f"{seconds} s"


class ModelLadder:
    """Coordena tentativas de modelos e cooldowns locais.

    Mantem uma sequencia configurada, ignora degraus em cooldown e retorna a primeira resposta que funcionar.
    O custo e O(N) por rodada no pior caso, onde N e o numero de modelos configurados.
    """

    def __init__(
        self,
        models: tuple[str, ...] | list[str],
        *,
        clock: Callable[[], float] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        normalizados = tuple(str(model).strip() for model in models if str(model).strip())
        if not normalizados:
            raise ValueError("A escada de modelos precisa de pelo menos um modelo.")
        if len(set(normalizados)) != len(normalizados):
            raise ValueError("A escada de modelos nao pode conter modelos repetidos.")
        self._models = normalizados
        self._clock = clock or time.monotonic
        self._logger = logger or logging.getLogger(__name__)
        self._cooldown_until: dict[str, float] = {}

    @property
    def modelos(self) -> tuple[str, ...]:
        return self._models

    def cooldown_restante(self, model: str) -> float:
        """Retorna os segundos restantes de cooldown de um modelo.

        Expiracoes sao removidas quando observadas, mantendo o estado pequeno.
        O custo e O(1).
        """
        until = self._cooldown_until.get(model)
        if until is None:
            return 0.0
        restante = until - float(self._clock())
        if restante <= 0:
            self._cooldown_until.pop(model, None)
            return 0.0
        return restante

    def esta_em_cooldown(self, model: str) -> bool:
        """Informa se um modelo ainda deve ser ignorado.

        Usa o relogio injetado e compartilha a mesma fonte de verdade de cooldown_restante.
        O custo e O(1).
        """
        return self.cooldown_restante(model) > 0.0

    def _proximo_disponivel(self) -> str | None:
        for model in self._models:
            if not self.esta_em_cooldown(model):
                return model
        return None

    def _falha_exaurida(self, last_error: Exception | None = None) -> ModelLadderExhaustedError:
        remaining = {
            model: self.cooldown_restante(model)
            for model in self._models
            if self.esta_em_cooldown(model)
        }
        return ModelLadderExhaustedError(self._models, remaining, last_error=last_error)

    def executar(self, chamada: Callable[[str], Any]) -> tuple[str, Any]:
        """Tenta os modelos configurados ate obter uma resposta.

        Apenas falhas com politica conhecida movem a escada; 400/401 e erros desconhecidos sobem sem troca.
        O custo e O(N) decisoes locais mais as chamadas realmente feitas ao provider.
        """
        while True:
            model = self._proximo_disponivel()
            if model is None:
                raise self._falha_exaurida()

            try:
                return model, chamada(model)
            except Exception as error:
                politica = _politica_de_falha(error)
                if politica is None:
                    raise

                _, seconds = politica
                self._cooldown_until[model] = float(self._clock()) + seconds
                proximo = self._proximo_disponivel()
                if proximo is None:
                    raise self._falha_exaurida(last_error=error) from error

                self._logger.warning(
                    "modelo %s em cooldown por %s, usando %s",
                    model,
                    _formatar_duracao(seconds),
                    proximo,
                )
