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
    hostname = (parsed.hostname or "").lower().removeprefix("www.")
    port = parsed.port
    default_port = (scheme == "https" and port == 443) or (scheme == "http" and port == 80)
    netloc = hostname
    if port is not None and not default_port:
        netloc = f"{netloc}:{port}"
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
    dados_acao: Any = None,
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

    if ferramenta == "preencher_elemento":
        return _controle_com_valor(
            str(dados.get("pagina") or ""),
            str(args.get("alvo") or ""),
            str(args.get("texto") or ""),
            int(args.get("indice") or 1),
        )

    if ferramenta == "rolar_pagina":
        return _verificar_rolagem(
            str(args.get("direcao") or ""),
            dados.get("scroll"),
            dados_acao,
        )

    return None


def _controle_com_valor(pagina: str, alvo: str, esperado: str, indice: int) -> bool | None:
    alvo_normalizado = str(alvo or "").strip().casefold()
    if not alvo_normalizado:
        return None

    linhas = [
        linha.strip()
        for linha in str(pagina or "").splitlines()
        if "valor=" in linha and linha.strip().startswith("-")
    ]
    candidatas = [
        linha for linha in linhas
        if alvo_normalizado in linha.casefold()
    ]
    if not candidatas:
        return None

    # Campos sensiveis sao mascarados pelo leitor da pagina. Nao tentamos
    # inferir o segredo nem tratamos o mascaramento como falha.
    esperado_texto = str(esperado or "")
    if "[REDACTED]" in " ".join(candidatas):
        return None

    matches = [
        linha for linha in candidatas
        if f"valor={esperado_texto}" in linha
    ]
    return len(matches) >= max(1, int(indice or 1))




def _numero_scroll(dados: Any, chave: str) -> float | None:
    if not isinstance(dados, dict):
        return None
    try:
        return float(dados.get(chave))
    except (TypeError, ValueError):
        return None


def _verificar_rolagem(
    direcao: str,
    scroll_atual: Any,
    dados_acao: Any,
) -> bool | None:
    if not isinstance(scroll_atual, dict) or not isinstance(dados_acao, dict):
        return None

    atual = _numero_scroll(scroll_atual, "scroll_y")
    antes = _numero_scroll(dados_acao, "scroll_y_antes")
    depois = _numero_scroll(dados_acao, "scroll_y_depois")
    altura = _numero_scroll(dados_acao, "scroll_height")
    viewport = _numero_scroll(dados_acao, "viewport_height")
    if None in {atual, antes, depois, altura, viewport}:
        return None

    tolerancia = 8.0
    if abs(atual - depois) > tolerancia:
        return False

    max_scroll = max(0.0, altura - viewport)

    if direcao == "inicio":
        return atual <= tolerancia

    if direcao == "fim":
        return abs(atual - max_scroll) <= tolerancia

    if max_scroll <= tolerancia:
        return None

    if direcao == "baixo":
        if depois > antes + 1.0:
            return True
        return depois >= max_scroll - tolerancia

    if direcao == "cima":
        if depois < antes - 1.0:
            return True
        return depois <= tolerancia

    return None
