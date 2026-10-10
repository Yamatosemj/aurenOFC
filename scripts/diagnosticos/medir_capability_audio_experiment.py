import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.capability_audio_experiment import run_experiment

if __name__ == "__main__":
    import json

    result = run_experiment()
    path = PROJECT_ROOT / "logs" / "testes" / "EXPERIMENTO_CAPABILITY_AUDIO_V43.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"JSON salvo em: {path}")
