from __future__ import annotations

from typing import Any
import os
from dataclasses import replace

from config import CACHE_KEY, MODEL
from core.prompt import instrucoes
from core import usage
from core.intent_verification import INSTRUCTIONS, RESPONSE_FORMAT, IntentVerificationFailure, criar_entrada_verificacao, interpretar_decisao


class OpenAIProvider:
    """Adaptador do provedor atual.

    Esta classe concentra todo o conhecimento sobre o SDK da OpenAI.
    Trocar de provedor depois nao exige mexer no Core, no Router ou nas Tools.
    """

    name = "openai"

    def __init__(self) -> None:
        self._client = None

    def get_client(self):
        if self._client is None:
            from openai import OpenAI
            # Live tests must not multiply requests or wait the SDK's default
            # ten minutes. Production configuration remains unchanged.
            options = {"timeout": 45.0, "max_retries": 0} if os.getenv("AUREN_TEST_MODE") == "1" else {}
            self._client = OpenAI(**options)
        return self._client

    @staticmethod
    def _normalizar_tools(toolset):
        # None significa manter o registry completo atual por compatibilidade.
        if toolset is None:
            from core.tools_registry import tools as default_tools
            return default_tools
        return toolset

    def create_response(
        self,
        entrada: Any,
        *,
        response_id: str | None = None,
        reasoning_effort: str = "none",
        tool_choice: str | dict | None = None,
        tools=None,
    ) -> Any:
        parametros = {
            "model": MODEL,
            "instructions": instrucoes,
            "tools": self._normalizar_tools(tools),
            "input": entrada,
            "parallel_tool_calls": False,
            "reasoning": {"effort": reasoning_effort},
            "prompt_cache_key": CACHE_KEY,
            "prompt_cache_options": {"ttl": "30m"},
        }
        if tool_choice is not None:
            parametros["tool_choice"] = tool_choice
        if response_id:
            parametros["previous_response_id"] = response_id

        resposta = self.get_client().responses.create(**parametros)
        usage.registrar_uso(resposta)
        return resposta

    def verify_intent(self, objetivo, chamadas, historico):
        """Segunda leitura sem ferramentas: nenhuma acao e executada nesta chamada."""
        entrada = criar_entrada_verificacao(objetivo, chamadas, historico)
        try:
            resposta = self.get_client().responses.create(
                model=MODEL,
                instructions=INSTRUCTIONS,
                input=entrada,
                tools=[],
                reasoning={"effort": "none"},
                text={"format": RESPONSE_FORMAT},
                max_output_tokens=300,
                store=False,
            )
        except Exception as exc:
            raise IntentVerificationFailure("Falha ao consultar o revisor; uso desconhecido.") from exc
        usage.registrar_uso(resposta)
        try:
            decisao = interpretar_decisao(getattr(resposta, "output_text", ""))
        except ValueError as exc:
            raise IntentVerificationFailure("Resposta invalida do revisor.", usage.extrair_metricas_uso(resposta) or None) from exc
        return replace(decisao, metricas_uso=usage.extrair_metricas_uso(resposta))
