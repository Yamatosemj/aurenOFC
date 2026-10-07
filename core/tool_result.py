from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping


LEGACY_FAILURE_MARKERS = (
    "acao nao executada:",
    "acao nao executada",
    "ação não executada:",
    "nao consegui",
    "não consegui",
    "nao encontrei",
    "não encontrei",
    "nao foi possivel",
    "não foi possível",
    "falha ao executar",
    "falha inesperada",
    "usuario negou",
    "usuário negou",
    "preenchimento nao confirmado",
    "preenchimento não confirmado",
    "volume invalido",
    "volume inválido",
    "coordenadas fora",
    "posicao fora",
    "posição fora",
    "tecla vazia",
    "nao reconheco a tecla",
    "não reconheço a tecla",
    "indice invalido",
    "índice inválido",
    "indice de aba invalido",
    "índice de aba inválido",
    "nao existe a aba",
    "não existe a aba",
    "nao vou encerrar",
    "não vou encerrar",
    "alvo ambiguo",
    "alvo ambíguo",
    "tamanho muito pequeno",
    "tamanho muito grande",
    "direcao invalida",
    "direção inválida",
    "botao invalido",
    "botão inválido",
    "acao de midia invalida",
    "ação de mídia inválida",
    "pid invalido",
    "pid inválido",
    "o estado do mudo deve ser",
)


@dataclass(frozen=True)
class ToolResult:
    """Resultado estruturado de uma ferramenta do Auren.

    A mensagem continua sendo a representação que o modelo recebe. Os campos
    estruturados existem para que o runtime nao precise adivinhar sucesso ou
    falha olhando para o texto devolvido pela ferramenta.
    """

    ok: bool
    message: str
    data: Mapping[str, Any] | None = None
    error_code: str | None = None
    tool_name: str | None = None
    conteudo_nao_confiavel: bool = False

    @classmethod
    def success(
        cls,
        message: str,
        *,
        data: Mapping[str, Any] | None = None,
        tool_name: str | None = None,
        conteudo_nao_confiavel: bool = False,
    ) -> "ToolResult":
        return cls(
            ok=True,
            message=str(message),
            data=data,
            tool_name=tool_name,
            conteudo_nao_confiavel=conteudo_nao_confiavel,
        )

    @classmethod
    def failure(
        cls,
        message: str,
        *,
        error_code: str = "tool_error",
        data: Mapping[str, Any] | None = None,
        tool_name: str | None = None,
        conteudo_nao_confiavel: bool = False,
    ) -> "ToolResult":
        return cls(
            ok=False,
            message=str(message),
            data=data,
            error_code=error_code,
            tool_name=tool_name,
            conteudo_nao_confiavel=conteudo_nao_confiavel,
        )

    def for_model(self) -> str:
        """Representacao compacta e estavel enviada de volta ao modelo."""
        if self.data is None and self.error_code is None:
            return self.message

        payload: dict[str, Any] = {
            "ok": self.ok,
            "mensagem": self.message,
        }
        if self.conteudo_nao_confiavel:
            payload["conteudo_nao_confiavel"] = True
        if self.error_code:
            payload["codigo_erro"] = self.error_code
        if self.data is not None:
            payload["dados"] = dict(self.data)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": self.ok,
            "mensagem": self.message,
        }
        if self.error_code:
            payload["codigo_erro"] = self.error_code
        if self.data is not None:
            payload["dados"] = dict(self.data)
        if self.tool_name:
            payload["ferramenta"] = self.tool_name
        if self.conteudo_nao_confiavel:
            payload["conteudo_nao_confiavel"] = True
        return payload

    def __str__(self) -> str:
        return self.for_model()


def from_legacy(value: Any, *, tool_name: str | None = None) -> ToolResult:
    """Converte retornos antigos para o novo contrato durante a migração.

    O fallback textual existe apenas para ferramentas ainda nao migradas. Toda
    ferramenta nova deve retornar ToolResult diretamente.
    """
    if isinstance(value, ToolResult):
        if value.tool_name == tool_name or tool_name is None:
            return value
        return ToolResult(
            ok=value.ok,
            message=value.message,
            data=value.data,
            error_code=value.error_code,
            tool_name=tool_name,
            conteudo_nao_confiavel=value.conteudo_nao_confiavel,
        )

    if isinstance(value, dict) and isinstance(value.get("ok"), bool):
        ok = bool(value.get("ok"))
        message = value.get("mensagem") or value.get("message") or value.get("erro")
        if message is None:
            message = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return ToolResult(
            ok=ok,
            message=str(message),
            data=value,
            error_code=(str(value.get("codigo_erro")) if value.get("codigo_erro") else None),
            tool_name=tool_name,
        )

    if isinstance(value, dict):
        message = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return ToolResult.success(message, data=value, tool_name=tool_name)

    texto = str(value or "")
    normalizado = texto.strip().lower()
    falhou = any(
        normalizado.startswith(marcador)
        or (
            marcador == "acao nao executada"
            and marcador in normalizado
        )
        for marcador in LEGACY_FAILURE_MARKERS
    )
    if falhou:
        return ToolResult.failure(
            texto,
            error_code="legacy_text_error",
            tool_name=tool_name,
        )
    return ToolResult.success(texto, tool_name=tool_name)
