import importlib


def test_legacy_runner_is_only_a_compatibility_facade():
    legacy = importlib.import_module("testes_auren")
    live = importlib.import_module("testes_auren_live")

    assert legacy.main is live.main
    assert legacy.run_model_suite is live.run_model_suite
    assert legacy.main.__module__ == "testes_auren_live"


def test_live_runner_remains_outside_pytest_collection_pattern():
    assert not "test_".startswith("testes_auren_live")
