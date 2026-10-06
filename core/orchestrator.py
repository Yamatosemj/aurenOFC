from __future__ import annotations

from typing import Any

from brains.deep import DeepBrain
from brains.fast import FastBrain
from core.router import Router, get_router
from core.tools_registry import tools as TOOL_REGISTRY
from providers.openai_provider import OpenAIProvider
from config import ARCHITECTURE_NAME, MODEL
from core.prompt import instrucoes
from agent.ari_native.response_cache import ResponseCache, build_response_cache_key
from agent.ari_native.llm_router import LLMRouter


class _CachedResponse:
    """Objeto minimo compativel com o contrato Responses usado pelo Harness."""

    def __init__(self, output_text: str, cache_key: str) -> None:
        self.output_text = str(output_text or "")
        self.output = []
        self.id = "cached:" + cache_key[:16]
        self.usage = None


class AurenOrchestrator:
    """Coordena Router -> Brain -> Model Provider.

    O Router tambem seleciona o conjunto de ferramentas da rodada. Em tarefas
    ambiguas ele conserva as 44 ferramentas da V43; em tarefas claramente
    classificadas envia apenas o subconjunto pertinente.
    """

    def __init__(self, *, provider=None, router: Router | None = None) -> None:
        self.provider = provider or OpenAIProvider()
        self.router = router or get_router()
        self.brains = {
            "fast": FastBrain(self.provider),
            "deep": DeepBrain(self.provider),
        }
        self.response_cache = ResponseCache.from_config()
        self.llm_router = LLMRouter()

    def get_client(self):
        getter = getattr(self.provider, "get_client", None)
        if getter is None:
            raise AttributeError("O provider atual nao expõe get_client().")
        return getter()

    @staticmethod
    def _cacheable_input(entrada: Any, tool_choice: str | dict | None) -> bool:
        """Somente conversas estáveis e sem execução podem entrar no cache."""
        if tool_choice is not None or not isinstance(entrada, str):
            return False
        from core.utils import normalizar_nome
        texto = " ".join(entrada.split()).lower()
        texto_norm = normalizar_nome(texto)
        if not texto or len(texto) > 700:
            return False
        # Estado do computador, web atual e ações nunca devem ser congelados.
        dinamicos = (
            "que horas", "qual a hora", "hora agora", "data de hoje", "agora",
            "status", "ram", "memoria usada", "janela", "aba", "clipboard",
            "captura", "screenshot", "tela", "volume", "processo", "atual",
            "hoje", "agora", "current", "latest", "news",
        )
        if any(token in texto or token in texto_norm for token in dinamicos):
            return False
        # Ações que deveriam produzir function_call não podem ser cacheadas
        # caso o modelo eventualmente responda apenas em linguagem natural.
        acoes = (
            "abra ", "abrir ", "abre ", "clique", "clicar", "preencha",
            "digite", "pesquise", "pesquisar", "navegue", "navegar",
            "feche ", "fechar ", "mova ", "defina ", "coloque ",
            "salve ", "salvar ", "execute ", "rodar ", "analise a tela",
        )
        return not any(token in texto or token in texto_norm for token in acoes)

    def _cache_key(self, entrada: str, requested_brain: str | None) -> str:
        return build_response_cache_key(
            entrada,
            provider=getattr(self.provider, "name", "openai"),
            model=MODEL,
            system_prompt=instrucoes,
            personality=ARCHITECTURE_NAME,
            scenario=requested_brain or "auto",
            history_instruction="Auren V44 Ari Fusion safe response cache",
            include_context=True,
        )

    def create_response(
        self,
        entrada: Any,
        *,
        response_id: str | None = None,
        reasoning_effort: str = "none",
        tool_choice: str | dict | None = None,
        requested_brain: str | None = None,
    ) -> Any:
        auto_brain = requested_brain
        if auto_brain is None and isinstance(entrada, str):
            auto_brain = self.llm_router.route(entrada).role
        brain_name = self.router.route(
            entrada,
            tool_choice=tool_choice,
            reasoning_effort=reasoning_effort,
            requested_brain=auto_brain,
        )

        cache_key = None
        if self._cacheable_input(entrada, tool_choice):
            cache_key = self._cache_key(entrada, brain_name)
            cached = self.response_cache.get(cache_key)
            if cached is not None:
                return _CachedResponse(cached, cache_key)

        toolset = self.router.select_tools(entrada, TOOL_REGISTRY)
        brain = self.brains[brain_name]
        resposta = brain.create_response(
            entrada,
            response_id=response_id,
            reasoning_effort=reasoning_effort,
            tool_choice=tool_choice,
            tools=toolset,
        )

        if cache_key is not None:
            try:
                output = list(getattr(resposta, "output", []) or [])
                has_function_call = any(getattr(item, "type", "") == "function_call" for item in output)
                text = str(getattr(resposta, "output_text", "") or "").strip()
                if text and not has_function_call:
                    self.response_cache.set(cache_key, text)
            except Exception:
                # Cache é otimização; nunca pode afetar a execução principal.
                pass

        return resposta

    def get_response_cache_stats(self) -> dict[str, int]:
        return self.response_cache.stats()
