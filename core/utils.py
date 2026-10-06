from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


def normalizar_nome(texto):
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        c for c in texto
        if not unicodedata.combining(c)
    )
    texto = texto.lower()
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return " ".join(texto.split())


def similaridade_nome(a, b):
    """Retorna similaridade 0..1 para nomes sujeitos a erros de ASR."""
    a_norm = normalizar_nome(a).replace(" ", "")
    b_norm = normalizar_nome(b).replace(" ", "")
    if not a_norm or not b_norm:
        return 0.0
    if a_norm == b_norm:
        return 1.0
    return SequenceMatcher(None, a_norm, b_norm).ratio()
