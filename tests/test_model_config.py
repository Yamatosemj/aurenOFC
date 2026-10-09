import importlib
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

import config


ROOT = Path(__file__).resolve().parents[1]


def _reload_config():
    return importlib.reload(config)


@pytest.fixture(autouse=True)
def _restore_config_module_after_test():
    had_model = "AUREN_MODEL" in os.environ
    original_model = os.environ.get("AUREN_MODEL")
    yield
    if had_model:
        os.environ["AUREN_MODEL"] = original_model or ""
    else:
        os.environ.pop("AUREN_MODEL", None)
    importlib.reload(config)


def test_default_model_is_gpt_5_6_luna(monkeypatch):
    monkeypatch.delenv("AUREN_MODEL", raising=False)
    loaded = _reload_config()
    assert loaded.DEFAULT_MODEL == "gpt-5.6-luna"
    assert loaded.MODEL == "gpt-5.6-luna"


def test_model_can_be_overridden_by_environment(monkeypatch):
    monkeypatch.setenv("AUREN_MODEL", "gpt-5.6-terra")
    loaded = _reload_config()
    assert loaded.MODEL == "gpt-5.6-terra"


def test_config_module_is_restored_after_override_test():
    expected = os.getenv("AUREN_MODEL", "").strip() or "gpt-5.6-luna"
    assert config.MODEL == expected


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


def _run_clean_auren_import(model: str | None):
    env = os.environ.copy()
    if model is None:
        env.pop("AUREN_MODEL", None)
    else:
        env["AUREN_MODEL"] = model

    code = "import auren, config; assert auren.MODEL == config.MODEL; print(auren.MODEL)"
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_auren_import_uses_environment_model_in_clean_subprocess():
    result = _run_clean_auren_import("outro-modelo")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "outro-modelo"


def test_auren_import_uses_default_model_without_environment_in_clean_subprocess():
    result = _run_clean_auren_import(None)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "gpt-5.6-luna"


def test_compatibility_model_literal_remains_readable_from_source():
    source = (ROOT / "auren.py").read_text(encoding="utf-8")
    assert re.search(r'MODEL\s*=\s*["\']gpt-5\.6-luna["\']', source)
