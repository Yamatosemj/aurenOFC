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
