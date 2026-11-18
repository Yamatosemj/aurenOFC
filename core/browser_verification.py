"""Verificacao deterministica de resultados de acoes do navegador.

Este modulo nao executa ferramentas nem acessa o navegador. Ele apenas compara
argumentos da acao com dados estruturados produzidos por uma leitura posterior.
"""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qs, urljoin, urlsplit

from core.utils import normalizar_nome


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
    if not hostname:
        return ""
    try:
        port = parsed.port
    except ValueError:
        return ""
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


def contexto_resultados(dados: Any) -> dict[str, Any] | None:
    """Retem apenas a URL ativa e os links observados na pagina de busca."""
    if not isinstance(dados, dict):
        return None
    ativa = _active_tab(str(dados.get('abas') or ''))
    if ativa is None:
        return None
    pagina = str(dados.get('pagina') or '')
    candidatos = pagina.split('Candidatos de link na ordem da pagina:', 1)
    trecho = candidatos[1] if len(candidatos) == 2 else pagina
    links = []
    for linha in trecho.splitlines():
        match = re.match(r'^- (?:posicao=\d+ \| )?texto=(.*?) \| href=(\S+)',
                         linha.strip())
        if match:
            url = urljoin(ativa[2], match.group(2))
            if urlsplit(url).scheme in {'http', 'https'} and _normalize_url(url):
                links.append({'titulo': match.group(1).strip(), 'url': url})
        if len(links) >= 20:
            break
    return {'url': ativa[2], 'links': links}


def destino_resultado(
    contexto: dict[str, Any], ferramenta: str, argumentos: str, indice: int | None,
) -> dict[str, str] | None:
    """Vincula a acao a um link observado antes da abertura."""
    args = _parse_args(argumentos)
    if args is None or not contexto.get('links'):
        return None
    links = contexto['links']
    escolhido = None
    if ferramenta == 'navegar_navegador':
        url = _normalize_url(str(args.get('url') or ''))
        if url:
            escolhido = next((item for item in links
                              if _normalize_url(item['url']) == url), None)
    elif ferramenta == 'clicar_elemento':
        alvo = normalizar_nome(str(args.get('alvo') or ''))
        escolhido = next((item for item in links
                          if alvo and (alvo == normalizar_nome(item['titulo'])
                                       or alvo in normalizar_nome(item['titulo']))), None)
    if escolhido is None or (indice is not None and links.index(escolhido) != indice - 1):
        return None
    return {'url': escolhido['url'], 'titulo': escolhido['titulo']}


def confirmar_destino_resultado(
    contexto_antes: dict[str, Any], destino: dict[str, str], dados_depois: Any,
) -> bool:
    """Exige mudanca de pagina e URL compatível com o link escolhido."""
    if not isinstance(dados_depois, dict):
        return False
    ativa = _active_tab(str(dados_depois.get('abas') or ''))
    if ativa is None:
        return False
    _indice, titulo, observado = ativa
    anterior = _normalize_url(str(contexto_antes.get('url') or ''))
    observado_norm = _normalize_url(observado)
    if not observado_norm or observado_norm == anterior:
        return False
    esperado = _normalize_url(destino['url'])
    if observado_norm == esperado:
        return True
    # Links de busca podem apontar para um redirecionador explicito.
    parsed = urlsplit(destino['url'])
    for key in ('url', 'q', 'target'):
        for value in parse_qs(parsed.query).get(key, []):
            if value.startswith(('http://', 'https://')) and _normalize_url(value) == observado_norm:
                return True
    # Redirecionamento no mesmo host com o titulo esperado. Nao inferir
    # legitimidade de um dominio diferente apenas pelo texto da pagina.
    expected_host = (urlsplit(esperado).hostname or '').removeprefix('www.')
    observed_host = (urlsplit(observado_norm).hostname or '').removeprefix('www.')
    expected_slug = urlsplit(esperado).path.rstrip('/').rsplit('/', 1)[-1]
    observed_slug = urlsplit(observado_norm).path.rstrip('/').rsplit('/', 1)[-1]
    return bool(expected_host and expected_host == observed_host
                and expected_slug and expected_slug == observed_slug
                and len(normalizar_nome(destino['titulo'])) >= 8
                and normalizar_nome(titulo) == normalizar_nome(destino['titulo']))


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
