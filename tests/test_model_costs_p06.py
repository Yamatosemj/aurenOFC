"""Regressoes offline da estimativa de custos por modelo (P06)."""

import json
import sqlite3
from datetime import date
from types import SimpleNamespace

import pytest

from core import usage
from core.task_trace import SCHEMA_VERSION, TaskTraceStore


@pytest.mark.parametrize("model,expected", [
    ("gpt-5.6-luna", 2.74),
    ("gpt-5.6-terra", 27.4),
    ("gpt-5.6-sol", 48.8),
])
def test_model_specific_prices_and_cache_subsets(model, expected):
    metrics = {"input_tokens": 3_000_000, "cached_tokens": 1_000_000,
               "cache_write_tokens": 1_000_000, "output_tokens": 1_000_000}
    # Contexto longo: entrada 2x, saida 1.5x.
    assert usage.calcular_custo_estimado(metrics, model, on_date=date(2026, 11, 25)) == pytest.approx(expected)


def test_promotional_sol_rate_is_not_guessed_after_expiry():
    assert usage.calcular_custo_estimado({"input_tokens": 1}, "gpt-5.6-sol",
                                         on_date=date(2026, 12, 1)) is None


def test_short_context_cache_read_write_and_output_are_charged_once():
    metrics = {"input_tokens": 1000, "cached_tokens": 200, "cache_write_tokens": 300,
               "output_tokens": 100}
    # 500 ordinary, 200 cache reads, 300 writes; 100 output tokens.
    assert usage.calcular_custo_estimado(metrics, "gpt-5.6-luna") == pytest.approx(
        (500 * 0.20 + 200 * 0.02 + 300 * 0.25 + 100 * 1.20) / 1_000_000)


def test_unknown_model_missing_usage_invalid_cache_and_real_zero():
    one = {"input_tokens": 1, "output_tokens": 0}
    assert usage.calcular_custo_estimado(one, "unpriced-model") is None
    assert usage.calcular_custo_estimado(None, "gpt-5.6-luna") is None
    assert usage.calcular_custo_estimado({"input_tokens": 1, "cached_tokens": 2}, "gpt-5.6-luna") is None
    assert usage.calcular_custo_estimado({"input_tokens": 0, "output_tokens": 0}, "gpt-5.6-luna") == 0.0


def test_task_known_partial_unknown_and_report(tmp_path):
    store = TaskTraceStore(tmp_path / "costs.sqlite3")
    known = store.start_task(task_id="known", chat_id=None, objective="known")
    known.record_model(1, 1, {"input_tokens": 1_000, "output_tokens": 1_000}, model="gpt-5.6-luna")
    known.record_provider_call("verification", 1, success=True,
                               usage={"input_tokens": 1_000, "output_tokens": 0}, model="gpt-5.6-terra")
    known.finish(status="completed", total_ms=2)
    row = store.get_task("known")
    assert row["cost_usd"] == pytest.approx(0.0034)
    assert row["cost_status"] == "estimated"
    assert row["cost_known_calls"] == 2
    spans = store.get_spans("known")
    assert [json.loads(s["metadata_json"])["model"] for s in spans] == ["gpt-5.6-luna", "gpt-5.6-terra"]
    assert all(json.loads(s["metadata_json"])["price_reference"] == usage.PRICE_REFERENCE for s in spans)

    partial = store.start_task(task_id="partial", chat_id=None, objective="partial")
    partial.record_model(1, 1, {"input_tokens": 1_000}, model="gpt-5.6-luna")
    partial.record_provider_call("verification", 1, success=False, usage=None)
    partial.finish(status="failed", total_ms=2)
    assert store.get_task("partial")["cost_status"] == "partial"
    assert store.get_task("partial")["cost_usd"] == pytest.approx(0.0002)

    unknown = store.start_task(task_id="unknown", chat_id=None, objective="unknown")
    unknown.record_model(1, 1, {"input_tokens": 1_000_000}, model="unpriced-model")
    unknown.finish(status="completed", total_ms=2)
    assert store.get_task("unknown")["cost_status"] == "unknown"
    assert store.report()["by_type"]["agentic"]["median_cost_usd"] == row["cost_usd"]


def test_session_and_task_use_same_price_without_double_count(tmp_path, monkeypatch):
    for name in ("session_input_tokens", "session_output_tokens", "session_cached_tokens",
                 "session_cache_write_tokens", "session_cost", "session_cost_known_calls", "session_cost_unknown_calls"):
        monkeypatch.setattr(usage, name, 0)
    store = TaskTraceStore(tmp_path / "consistent.sqlite3")
    trace = store.start_task(task_id="one", chat_id=None, objective="one")
    response = SimpleNamespace(model="gpt-5.6-luna", usage=SimpleNamespace(
        input_tokens=1000, output_tokens=100,
        input_tokens_details=SimpleNamespace(cached_tokens=200, cache_write_tokens=300)))
    metrics = usage.extrair_metricas_uso(response)
    trace.record_provider_call("response", 1, success=True, usage=metrics, model=response.model)
    trace.record_model(1, 1, metrics, model=response.model)
    usage.registrar_uso(response)
    trace.finish(status="completed", total_ms=1)
    row = store.get_task("one")
    assert row["cost_usd"] == pytest.approx(usage.session_cost)
    assert row["cost_known_calls"] == usage.session_cost_known_calls == 1
    assert (row["input_tokens"], row["cached_tokens"], row["cache_write_tokens"]) == (1000, 200, 300)


def test_schema_migration_preserves_legacy_cost(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE task_traces (task_id TEXT PRIMARY KEY, cost_usd REAL NOT NULL)")
        connection.execute("INSERT INTO task_traces VALUES ('old', 12.34)")
        connection.execute("PRAGMA user_version = 1")
    row = TaskTraceStore(path).get_task("old")
    assert row["cost_usd"] == 12.34
    assert row["cost_status"] == "legacy_unverified"
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
