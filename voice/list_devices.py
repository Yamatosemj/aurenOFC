from __future__ import annotations

import argparse

try:
    import sounddevice as sd
except ImportError:
    sd = None

from voice.audio_devices import (
    DEFAULT_LABEL,
    estado_dispositivos,
    listar_dispositivos,
    salvar_escolha,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Lista dispositivos de áudio do Auren e exibe a escolha atual."
    )
    parser.add_argument(
        "--entrada",
        help="salva este nome como microfone; use vazio para voltar ao padrão do sistema",
    )
    parser.add_argument(
        "--saida",
        help="salva este nome como saída TTS; use vazio para voltar ao padrão do sistema",
    )
    parser.add_argument(
        "--atualizar",
        action="store_true",
        help="ignora a cache e reconsulta o backend de áudio",
    )
    return parser


def _exibir_escolha(valor: str) -> str:
    return valor or DEFAULT_LABEL


def main() -> int:
    args = _parser().parse_args()

    if sd is None:
        print(
            "sounddevice ausente. Rode INSTALAR_VOZ.bat para habilitar "
            "a listagem de dispositivos."
        )
        return 2

    if args.entrada is not None:
        path = salvar_escolha("input", args.entrada)
        print(f"Microfone salvo em: {path}")
    if args.saida is not None:
        path = salvar_escolha("output", args.saida)
        print(f"Saída TTS salva em: {path}")

    try:
        entradas = listar_dispositivos("input", refresh=args.atualizar)
        saidas = listar_dispositivos("output", refresh=args.atualizar)
    except Exception as exc:
        print(f"Falha ao consultar dispositivos de áudio: {exc}")
        return 3

    escolhas = estado_dispositivos()

    print("DISPOSITIVOS DE ENTRADA")
    print("=" * 70)
    for nome in entradas:
        print(f"- {nome}")
    print(f"\nEscolha atual: {_exibir_escolha(escolhas.get('input', ''))}")

    print("\nDISPOSITIVOS DE SAÍDA")
    print("=" * 70)
    for nome in saidas:
        print(f"- {nome}")
    print(f"\nEscolha atual: {_exibir_escolha(escolhas.get('output', ''))}")

    print("\nA seleção é guardada por nome em um arquivo local fora do repositório.")
    print("Para trocar sem reiniciar o Auren, salve o novo nome enquanto ele estiver aberto.")
    print('Exemplo: py voice\\list_devices.py --saida "Meu Headset"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
