"""Validacao deterministica de tarefas com multiplas abas."""
from __future__ import annotations

import re
from urllib.parse import urlsplit
from core.browser_verification import _normalize_url

from core.capabilities import KNOWN_SERVICES
from core.utils import normalizar_nome


def _extrair_destinos_abas(objetivo: str) -> dict[int, str]:
    """Extrai destinos verificáveis para abas numeradas.

    Retorna apenas destinos cujo alvo pode ser comparado de forma segura
    pelo Core: serviços conhecidos ou URLs explícitas.
    """
    texto = str(objetivo or "").strip()
    if not texto:
        return {}

    ordinais = {
        "primeira": 1,
        "segunda": 2,
        "terceira": 3,
        "quarta": 4,
        "quinta": 5,
        "sexta": 6,
        "setima": 7,
        "sétima": 7,
        "oitava": 8,
        "nona": 9,
        "decima": 10,
        "décima": 10,
    }
    destinos: dict[int, str] = {}
    clausulas = re.split(r"\s+e\s+", texto, flags=re.IGNORECASE)
    padrao = re.compile(
        r"^(?:abrir|abre|abra|coloque|coloca|deixe|deixa|carregue|carrega)?\s*"
        r"(?:o|a|um|uma)?\s*(.+?)\s+(?:na|no)\s+"
        r"(primeira|segunda|terceira|quarta|quinta|sexta|setima|sétima|oitava|nona|decima|décima)\s+aba\b",
        flags=re.IGNORECASE,
    )

    for clausula in clausulas:
        match = padrao.search(clausula.strip())
        if not match:
            continue
        bruto = match.group(1).strip(" .,!? ")
        indice = ordinais[normalizar_nome(match.group(2))]

        url = re.search(r"https?://[^\s,;]+", bruto, flags=re.IGNORECASE)
        if url:
            destinos[indice] = url.group(0).rstrip(".,);]")
            continue

        chave = normalizar_nome(bruto)
        conhecido = KNOWN_SERVICES.get(chave)
        if conhecido:
            destinos[indice] = conhecido

    return destinos


def _multitab_concluida(objetivo: str, historico: list[dict[str, str]]) -> bool:
    """Confirma destinos de abas numeradas usando o ultimo estado real conhecido."""
    esperados = _extrair_destinos_abas(objetivo)
    if not esperados:
        return False

    estado = None
    for item in reversed(historico):
        if str(item.get("ferramenta", "")) == "listar_abas":
            estado = str(item.get("resultado", ""))
            break
    if not estado:
        return False

    for indice, esperado in esperados.items():
        match = re.search(
            rf"(?mi)^Aba\s+{indice}\s*:\s*(.+?)\s*\|\s*(https?://\S+)",
            estado,
        )
        if not match:
            return False

        url_atual = match.group(2).rstrip(".,);]")
        try:
            actual = urlsplit(_normalize_url(url_atual))
            target = urlsplit(_normalize_url(esperado))
            if (actual.scheme, actual.netloc) != (target.scheme, target.netloc):
                return False
            path = target.path.rstrip("/")
            if path and not (actual.path == path or actual.path.startswith(path + "/")):
                return False
            if target.query and actual.query != target.query:
                return False
        except ValueError:
            return False

    return True

