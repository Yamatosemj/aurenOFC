import importlib

import config


def _reload_config():
    return importlib.reload(config)


def test_default_model_is_gpt_5_6_luna(monkeypatch):
    monkeypatch.delenv("AUREN_MODEL", raising=False)
    loaded = _reload_config()
    assert loaded.DEFAULT_MODEL == "gpt-5.6-luna"
    assert loaded.MODEL == "gpt-5.6-luna"


def test_model_can_be_overridden_by_environment(monkeypatch):
    monkeypatch.setenv("AUREN_MODEL", "gpt-5.6-terra")
    loaded = _reload_config()
    assert loaded.MODEL == "gpt-5.6-terra"


def test_blank_model_environment_uses_safe_fallback(monkeypatch):
    monkeypatch.setenv("AUREN_MODEL", "   ")
    loaded = _reload_config()
    assert loaded.MODEL == loaded.DEFAULT_MODEL


def test_model_environment_is_trimmed(monkeypatch):
    monkeypatch.setenv("AUREN_MODEL", "  gpt-5.6-luna  ")
    loaded = _reload_config()
    assert loaded.MODEL == "gpt-5.6-luna"


def test_provider_uses_configured_model(monkeypatch):
    monkeypatch.setenv("AUREN_MODEL", "gpt-5.6-terra")
    loaded = _reload_config()

    import providers.openai_provider as provider_module

    try:
        provider_module = importlib.reload(provider_module)
        assert provider_module.MODEL == loaded.MODEL
    finally:
        monkeypatch.delenv("AUREN_MODEL", raising=False)
        importlib.reload(config)
        importlib.reload(provider_module)


def test_model_ladder_keeps_auren_model_as_first_rung(monkeypatch):
    monkeypatch.setenv("AUREN_MODEL", "gpt-5.6-terra")
    monkeypatch.setenv(
        "AUREN_MODEL_LADDER",
        "gpt-5.6-luna, gpt-5.6-mini, gpt-5.6-luna",
    )
    loaded = _reload_config()

    assert loaded.AUREN_MODEL_LADDER == (
        "gpt-5.6-luna",
        "gpt-5.6-mini",
    )
    assert loaded.MODEL_LADDER == (
        "gpt-5.6-terra",
        "gpt-5.6-luna",
        "gpt-5.6-mini",
    )


def test_model_ladder_without_environment_has_only_primary_model(monkeypatch):
    monkeypatch.delenv("AUREN_MODEL", raising=False)
    monkeypatch.delenv("AUREN_MODEL_LADDER", raising=False)
    loaded = _reload_config()
    assert loaded.MODEL_LADDER == (loaded.DEFAULT_MODEL,)


def test_request_timeout_is_configurable_and_positive(monkeypatch):
    monkeypatch.setenv("AUREN_REQUEST_TIMEOUT_S", "17.5")
    loaded = _reload_config()
    assert loaded.AUREN_REQUEST_TIMEOUT_S == 17.5


def test_invalid_request_timeout_uses_safe_default(monkeypatch):
    monkeypatch.setenv("AUREN_REQUEST_TIMEOUT_S", "0")
    loaded = _reload_config()
    assert loaded.AUREN_REQUEST_TIMEOUT_S == 30.0
