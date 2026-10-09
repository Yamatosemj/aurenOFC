"""Static discovery must follow the V47 UIA module without weakening checks."""
import importlib
import shutil


def test_live_discovery_accepts_native_uia_bridge(monkeypatch):
    live = importlib.import_module("testes_auren_live")
    monkeypatch.setattr(live, "RESULTS", [])
    assert live.run_discovery_tests() is True
    assert all(result.ok for result in live.RESULTS)


def test_live_discovery_rejects_bridge_without_password_protection(tmp_path, monkeypatch):
    live = importlib.import_module("testes_auren_live")
    original = live.ROOT
    for relative in ("auren.py", "core/facade.py", "core/tools_registry.py",
                     "tools/dispatcher.py", "tools/windows_uia.py"):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original / relative, target)
    bridge = tmp_path / "tools/windows_uia.py"
    bridge.write_text(bridge.read_text(encoding="utf-8").replace("IsPassword", "RemovedGuard"), encoding="utf-8")
    monkeypatch.setattr(live, "ROOT", tmp_path)
    monkeypatch.setattr(live, "RESULTS", [])
    assert live.run_discovery_tests() is False
    assert any(result.name == "UI Automation bridge" and not result.ok for result in live.RESULTS)


def test_functional_startup_failure_still_writes_result(tmp_path, monkeypatch):
    live = importlib.import_module("testes_auren_live")
    monkeypatch.setattr(live, "ROOT", tmp_path)
    monkeypatch.setattr(live, "RESULTS", [])
    monkeypatch.setattr(live, "ACTIVE_LAYERS", {"L0", "L1"})
    monkeypatch.setattr(live, "run_discovery_tests", lambda: True)
    def fail():
        raise RuntimeError("simulated setup failure")
    monkeypatch.setattr(live, "run_smoke_tests", fail)
    assert live.main() == 1
    report = tmp_path / "logs/testes/RESULTADO_TESTE_AUREN.txt"
    assert "Camadas funcionais interrompidas" in report.read_text(encoding="utf-8")
