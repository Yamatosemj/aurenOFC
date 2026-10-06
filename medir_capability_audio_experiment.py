from core.capability_audio_experiment import run_experiment

if __name__ == "__main__":
    import json
    from pathlib import Path

    result = run_experiment()
    path = Path(__file__).resolve().parent / "RELATORIOS" / "EXPERIMENTO_CAPABILITY_AUDIO_V43.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"JSON salvo em: {path}")
