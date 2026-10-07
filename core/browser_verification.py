"""Verificacao deterministica de resultados de acoes do navegador.

Este modulo nao executa ferramentas nem acessa o navegador. Ele apenas compara
argumentos da acao com dados estruturados produzidos por uma leitura posterior.
"""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlsplit


def _parse_args(arguments: str) -> dict[str, Any] | None:
    try:
        value = json.loads(str(arguments or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _normalize_url(value: str) -> str:
    url = str(value or "").strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url, flags=re.IGNORECASE):
        url = "https://" + url
    try:
        parsed = urlsplit(url)
    except ValueError:
        return url.rstrip("/")
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    return f"{scheme}://{netloc}{path}" + (f"?{parsed.query}" if parsed.query else "")


def _active_tab(abas: str) -> tuple[int, str, str] | None:
    texto = str(abas or "")
    active = re.search(r"(?m)^Aba ativa:\s*(\d+)", texto)
    if not active:
        return None

    indice = int(active.group(1))
    linha = re.search(
        rf"(?m)^Aba {indice}:\s*(?P<titulo>.*?)\s*\|\s*(?P<url>.+?)(?:\s*\[ATIVA\])?$",
        texto,
    )
    if not linha:
        return None

    return indice, linha.group("titulo").strip(), linha.group("url").strip()


def verificar_resultado_navegador(
    ferramenta: str,
    argumentos: str,
    dados_contexto: Any,
) -> bool | None:
    """Retorna True/False quando sabe verificar a acao; None para casos genericos."""
    dados = dados_contexto if isinstance(dados_contexto, dict) else {}
    abas = str(dados.get("abas") or "")
    args = _parse_args(argumentos)

    if args is None:
        return None

    ativa = _active_tab(abas)
    if ativa is None:
        return False if ferramenta in {
            "navegar_navegador",
            "abrir_nova_aba",
            "trocar_aba",
        } else None

    indice_atual, _titulo, url_atual = ativa

    if ferramenta in {"navegar_navegador", "abrir_nova_aba"}:
        esperado = _normalize_url(str(args.get("url") or ""))
        if not esperado:
            return None
        return _normalize_url(url_atual) == esperado

    if ferramenta == "trocar_aba":
        try:
            esperado = int(args.get("indice"))
        except (TypeError, ValueError):
            return None
        return indice_atual == esperado

    return None
