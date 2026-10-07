from __future__ import annotations

import logging
from typing import Any

from config import (
    AUREN_REQUEST_TIMEOUT_S,
    CACHE_KEY,
    MODEL,
    MODEL_LADDER,
)
from core.prompt import instrucoes
from core import usage
from providers.model_ladder import (
    ModelLadder,
    ModelLadderHistoryRequiredError,
)


logger = logging.getLogger(__name__)


class OpenAIProvider:
    """Adaptador do provedor atual.

    Esta classe concentra todo o conhecimento sobre o SDK da OpenAI.
    Trocar de provedor depois nao exige mexer no Core, no Router ou nas Tools.
    """

    name = "openai"

    def __init__(self) -> None:
        self._client = None
        self._ladder = ModelLadder(MODEL_LADDER, logger=logger)

    def get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(
                timeout=AUREN_REQUEST_TIMEOUT_S,
                max_retries=0,
            )
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
        historico_completo: Any | None = None,
    ) -> Any:
        """Cria uma resposta usando a escada configurada do provider.

        A primeira tentativa usa AUREN_MODEL; fallbacks usam o historico completo quando previous_response_id nao puder ser reaproveitado com seguranca.
        O custo e uma chamada por degrau tentado, sem retries internos do SDK.
        """
        tentativa_inicial = True

        def chamar(modelo: str) -> Any:
            nonlocal tentativa_inicial
            parametros = {
                "model": modelo,
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

            usa_continuacao = (
                bool(response_id)
                and tentativa_inicial
                and modelo == self._ladder.modelos[0]
            )
            if usa_continuacao:
                parametros["previous_response_id"] = response_id
            elif response_id:
                if historico_completo is None:
                    raise ModelLadderHistoryRequiredError(modelo)
                parametros["input"] = historico_completo

            tentativa_inicial = False
            return self.get_client().responses.create(**parametros)

        modelo_respondente, resposta = self._ladder.executar(chamar)
        usage.registrar_uso(resposta, modelo=modelo_respondente)
        return resposta
