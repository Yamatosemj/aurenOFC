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

    print("\nPara fixar um dispositivo de forma mais resiliente:")
    print('set AUREN_MIC_DEVICE="Nome exato do microfone"')
    print("O Auren resolve o nome novamente a cada abertura e cai para o padrao se o dispositivo desaparecer.")
    print("Indices numericos continuam aceitos apenas para compatibilidade.")
    print("A captura preserva a taxa suportada pelo dispositivo e o ASR normaliza para 16 kHz.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
