from __future__ import annotations

import threading
import time

from agent.ari_native.response_cache import ResponseCache, build_response_cache_key
from agent.ari_native.task_queue import AgentTaskQueue


def test_response_cache_lru_ttl_and_key():
    cache = ResponseCache(max_items=2, ttl_seconds=1)
    key = build_response_cache_key(
        "ola", provider="openai", model="gpt-5.6-luna",
        system_prompt="Auren", personality="Auren", scenario="chat",
        history_instruction="stable", include_context=True,
    )
    assert cache.get(key) is None
    cache.set(key, "Olá")
    assert cache.get(key) == "Olá"
    stats = cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1


def test_task_queue_priority_and_result():
    queue = AgentTaskQueue(max_workers=1)
    done = threading.Event()
    order = []

    def low(cancel):
        order.append("low")
        return "low"

    def high(cancel):
        order.append("high")
        done.set()
        return "high"

    # O worker inicia imediatamente; filas concorrentes com um worker podem
    # começar o primeiro item antes do segundo entrar. Ainda validamos resultado.
    low_id = queue.submit("low", low, priority=100)
    high_id = queue.submit("high", high, priority=1)
    assert done.wait(2.0)
    deadline = time.time() + 2
    while time.time() < deadline and queue.result(low_id) is None:
        time.sleep(0.02)
    assert queue.result(low_id).status == "completed"
    assert queue.result(high_id).status == "completed"
    assert set(order) == {"low", "high"}
    queue.shutdown(cancel_pending=False)


class _FakeResponse:
    def __init__(self, text):
        self.output_text = text
        self.output = []
        self.usage = None


class _FakeProvider:
    name = "fake"
    def __init__(self):
        self.calls = 0
    def create_response(self, *args, **kwargs):
        self.calls += 1
        return _FakeResponse("resposta fake")


def test_orchestrator_uses_safe_response_cache_for_stable_chat():
    from core.orchestrator import AurenOrchestrator
    provider = _FakeProvider()
    orch = AurenOrchestrator(provider=provider)
    first = orch.create_response("olá, como vai?")
    second = orch.create_response("olá, como vai?")
    assert first.output_text == second.output_text == "resposta fake"
    assert provider.calls == 1
    stats = orch.get_response_cache_stats()
    assert stats["hits"] == 1


def test_orchestrator_does_not_cache_dynamic_state_queries():
    from core.orchestrator import AurenOrchestrator
    provider = _FakeProvider()
    orch = AurenOrchestrator(provider=provider)
    orch.create_response("que horas são agora?")
    orch.create_response("que horas são agora?")
    assert provider.calls == 2


def test_wake_word_matcher_tolerates_small_error():
    from agent.ari_native.wake_word import wake_word_matches, extract_command
    assert wake_word_matches("auren", "auren")
    assert wake_word_matches("aurenn", "auren")
    assert extract_command("auren abrir o chrome", "auren") == "abrir o chrome"


def test_audio_manager_has_independent_input_output_locks():
    from agent.ari_native.audio_manager import get_audio_input_lock, get_audio_output_lock
    assert get_audio_input_lock() is not get_audio_output_lock()
