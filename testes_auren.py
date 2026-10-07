"""Compatibilidade com o runner legado.

A bateria live foi movida para testes_auren_live.py.
Este modulo permanece como fachada para scripts e comandos antigos.
"""

from testes_auren_live import *  # noqa: F401,F403
from testes_auren_live import main


if __name__ == "__main__":
    raise SystemExit(main())
