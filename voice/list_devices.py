from __future__ import annotations

try:
    import sounddevice as sd
except ImportError:
    sd = None


def main() -> int:
    if sd is None:
        print("sounddevice ausente. Rode INSTALAR_VOZ.bat para habilitar a listagem de microfones.")
        return 2
    print("DISPOSITIVOS DE ENTRADA DO WINDOWS")
    print("=" * 70)
    for index, info in enumerate(sd.query_devices()):
        if int(info.get("max_input_channels", 0)) > 0:
            print(
                f"[{index}] {info.get('name', '?')} | "
                f"entradas={info.get('max_input_channels', '?')} | "
                f"sample_rate={info.get('default_samplerate', '?')}"
            )
    print("\nPara fixar um dispositivo: set AUREN_MIC_DEVICE=12")
    print("O Auren preserva a taxa nativa do microfone e o ASR faz a conversao interna.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
