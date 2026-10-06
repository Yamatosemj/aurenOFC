from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.capability_audio_experiment import CASES, run_experiment
from core.router import Router


def test_audio_registry_experiment_resolves_all_cases_locally():
    result = run_experiment()
    summary = result["summary"]
    assert summary["registry_resolved"] == len(CASES)
    assert summary["registry_local"] == len(CASES)
    assert summary["registry_functionally_correct"] == len(CASES)


def test_audio_registry_experiment_does_not_change_legacy_router_behavior():
    router = Router()
    names = router.select_tool_names("volume 40%", __import__("core.tools_registry", fromlist=["tools"]).tools)
    assert "definir_volume_windows" in names
    assert len(names) == 7
    assert router.last_domains == ["audio"]


def test_audio_registry_experiment_never_calls_a_model():
    result = run_experiment()
    assert result["summary"]["model_calls_registry"] == 0
    assert result["summary"]["input_tokens_registry"] == 0
    assert result["summary"]["output_tokens_registry"] == 0
