"""Verificacao deterministica de resultados de acoes do navegador.

Este modulo nao executa ferramentas nem acessa o navegador. Ele apenas compara
argumentos da acao com dados estruturados produzidos por uma leitura posterior.
"""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin, urlsplit


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

    if ferramenta in {"abrir_nova_aba", "trocar_aba", "fechar_aba"}:
        return _verificar_abas(ferramenta, args, abas, dados_acao)

    ativa = _active_tab(abas)
    if ativa is None:
        return False if ferramenta == "navegar_navegador" else None

    indice_atual, _titulo, url_atual = ativa

    if ferramenta == "navegar_navegador":
        esperado = _normalize_url(str(args.get("url") or ""))
        if not esperado:
            return None
        return _normalize_url(url_atual) == esperado

    if ferramenta == "preencher_elemento":
        return _controle_com_valor(
            str(dados.get("pagina") or ""),
            str(args.get("alvo") or ""),
            str(args.get("texto") or ""),
            int(args.get("indice") or 1),
        )

    if ferramenta == "clicar_elemento":
        return _verificar_clique(
            dados.get("clique"),
            indice_atual,
            url_atual,
            str(dados.get("pagina") or ""),
        )

    if ferramenta == "rolar_pagina":
        return _verificar_rolagem(
            str(args.get("direcao") or ""),
            dados.get("scroll"),
            dados_acao,
        )

    return None


def _extrair_abas_observadas(abas: str) -> tuple[int | None, list[tuple[int, str, str]]]:
    texto = str(abas or "")
    match = re.search(r"(?m)^Abas abertas:\s*(\d+)", texto)
    quantidade = int(match.group(1)) if match else None
    encontradas: list[tuple[int, str, str]] = []
    for linha in texto.splitlines():
        match = re.match(
            r"^Aba\s+(\d+):\s*(.*?)\s*\|\s*(.+?)(?:\s*\[ATIVA\])?$",
            linha.strip(),
        )
        if match:
            encontradas.append(
                (int(match.group(1)), match.group(2).strip(), match.group(3).strip())
            )
    return quantidade, encontradas


def _snapshot_tab_active(snapshot: Any) -> tuple[int | None, str | None]:
    if not isinstance(snapshot, list):
        return None, None
    ativos = [item for item in snapshot if isinstance(item, dict) and item.get("ativa") is True]
    if len(ativos) != 1:
        return None, None
    item = ativos[0]
    try:
        indice = int(item.get("indice"))
    except (TypeError, ValueError):
        return None, None
    url = str(item.get("url") or "").strip()
    return indice, url


def _snapshot_is_consistent(snapshot: Any, expected_count: int) -> bool:
    if not isinstance(snapshot, list) or len(snapshot) != expected_count:
        return False
    if expected_count == 0:
        return True
    indices = []
    for item in snapshot:
        if not isinstance(item, dict):
            return False
        try:
            indices.append(int(item.get("indice")))
        except (TypeError, ValueError):
            return False
    if sorted(indices) != list(range(1, expected_count + 1)):
        return False
    return _snapshot_tab_active(snapshot)[0] is not None

def _verificar_abas(
    ferramenta: str,
    args: dict[str, Any],
    abas: str,
    dados_acao: Any,
) -> bool | None:
    quantidade_atual, observadas = _extrair_abas_observadas(abas)
    ativa = _active_tab(abas)

    # O texto observado precisa ser internamente consistente: a quantidade
    # declarada e o numero de linhas de abas devem contar a mesma historia.
    if quantidade_atual is not None and quantidade_atual != len(observadas):
        return False
    if quantidade_atual == 0 and observadas:
        return False

    info = dados_acao.get("abas") if isinstance(dados_acao, dict) else None
    if not isinstance(info, dict):
        # Compatibilidade com resultados antigos: ainda validamos destino/indice
        # quando a ferramenta nao fornece snapshot estruturado.
        if ferramenta == "trocar_aba" and ativa is not None:
            try:
                return ativa[0] == int(args.get("indice"))
            except (TypeError, ValueError):
                return None
        if ferramenta == "abrir_nova_aba":
            esperado = _normalize_url(str(args.get("url") or ""))
            return _normalize_url(ativa[2]) == esperado if esperado and ativa else None
        return None

    quantidade_antes = info.get("quantidade_antes")
    quantidade_depois = info.get("quantidade_depois")
    try:
        quantidade_antes_int = int(quantidade_antes)
        quantidade_depois_int = int(quantidade_depois)
    except (TypeError, ValueError):
        return None

    antes_snapshot = info.get("antes")
    depois_snapshot = info.get("depois")
    if isinstance(antes_snapshot, list) and not _snapshot_is_consistent(antes_snapshot, quantidade_antes_int):
        return False
    if isinstance(depois_snapshot, list) and not _snapshot_is_consistent(depois_snapshot, quantidade_depois_int):
        return False

    depois_ativo_indice, depois_ativo_url = _snapshot_tab_active(depois_snapshot)
    if isinstance(depois_snapshot, list) and quantidade_depois_int > 0:
        if depois_ativo_indice is None:
            return False
        if ativa is not None and depois_ativo_indice != ativa[0]:
            return False
        if depois_ativo_url and ativa is not None and _normalize_url(depois_ativo_url) != _normalize_url(ativa[2]):
            return False

    if ferramenta == "abrir_nova_aba":
        if quantidade_atual is None or quantidade_atual != quantidade_depois_int:
            return False
        if quantidade_depois_int != quantidade_antes_int + 1:
            return False

        esperado_indice = info.get("aba_ativa_depois")
        try:
            if ativa is None or ativa[0] != int(esperado_indice):
                return False
        except (TypeError, ValueError):
            return False

        esperado_url = str(args.get("url") or "").strip()
        if esperado_url:
            return _normalize_url(ativa[2]) == _normalize_url(esperado_url)

        return _normalize_url(ativa[2]) in {"about:blank", ""}

    if ferramenta == "trocar_aba":
        if quantidade_atual is None or quantidade_atual != quantidade_depois_int:
            return False
        try:
            esperado_indice = int(args.get("indice"))
        except (TypeError, ValueError):
            return None

        if ativa is None or ativa[0] != esperado_indice:
            return False

        try:
            if info.get("aba_ativa_depois") is not None and int(info["aba_ativa_depois"]) != esperado_indice:
                return False
        except (TypeError, ValueError):
            return False

        esperado_url = str(info.get("url_ativa_depois") or "").strip()
        if esperado_url:
            return _normalize_url(ativa[2]) == _normalize_url(esperado_url)
        return True

    if ferramenta == "fechar_aba":
        if quantidade_depois_int != quantidade_antes_int - 1:
            return False

        indice_solicitado = args.get("indice")
        indice_fechado = info.get("aba_fechada")
        if indice_solicitado is not None:
            try:
                solicitado = int(indice_solicitado)
                fechado = int(indice_fechado)
            except (TypeError, ValueError):
                return False
            if solicitado != 0 and fechado != solicitado:
                return False

        if quantidade_depois_int == 0:
            return quantidade_atual in {None, 0}

        if quantidade_atual is None or quantidade_atual != quantidade_depois_int:
            return False

        try:
            esperado_indice = int(info.get("aba_ativa_depois"))
        except (TypeError, ValueError):
            return None

        if ativa is None or ativa[0] != esperado_indice:
            return False

        esperado_url = str(info.get("url_ativa_depois") or "").strip()
        if esperado_url:
            return _normalize_url(ativa[2]) == _normalize_url(esperado_url)
        return True

    return None


def _linhas_controle(pagina: str) -> list[str]:
    return [
        linha.strip()
        for linha in str(pagina or "").splitlines()
        if linha.strip().startswith("- ") and "tag=" in linha
    ]


def _normalizar_valor_estado(valor: Any) -> str:
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if valor is None:
        return ""
    return str(valor).strip()


def _controle_corresponde_linha(
    linha: str,
    controle: Any,
) -> bool:
    if not isinstance(controle, dict):
        return False

    chave = str(controle.get("chave") or "").strip()
    if chave:
        return f"chave={chave}" in linha

    for campo, prefixo in (
        ("id", "id="),
        ("name", "name="),
        ("aria_label", "nome="),
        ("placeholder", "placeholder="),
    ):
        valor = str(controle.get(campo) or "").strip()
        if valor and f"{prefixo}{valor}" in linha:
            return True

    return False


def _estado_controle_na_linha(linha: str, atributo: str) -> str | None:
    marcador = "estado="
    if marcador not in linha:
        return None

    estado = linha.split(marcador, 1)[1]
    estado = estado.split(" | valor=", 1)[0]
    estado = estado.split(" |", 1)[0]

    prefixo = f"{atributo}="
    for item in estado.split(";"):
        item = item.strip()
        if item.startswith(prefixo):
            return item[len(prefixo):].strip()

    return None


def _verificar_clique(
    dados_clique: Any,
    indice_atual: int,
    url_atual: str,
    pagina: str = "",
) -> bool | None:
    if not isinstance(dados_clique, dict):
        return None

    atual = _normalize_url(url_atual)
    if dados_clique.get("navegacao"):
        if not atual:
            return False

        esperado = str(dados_clique.get("href") or "").strip()
        anterior = str(dados_clique.get("url_anterior") or "").strip()
        if esperado and esperado not in {"#", "#top"} and not esperado.lower().startswith("javascript:"):
            esperado = urljoin(anterior or url_atual, esperado)
            return atual == _normalize_url(esperado)

        if anterior:
            return atual != _normalize_url(anterior)

        return None

    efeito = dados_clique.get("efeito")
    if not isinstance(efeito, dict):
        return None

    sinal = efeito.get("sinal")
    controle = efeito.get("controle")
    if not isinstance(sinal, dict) or not isinstance(controle, dict):
        return None

    tipo = str(sinal.get("tipo") or "")
    if tipo == "controle":
        atributo = str(sinal.get("atributo") or "").strip()
        esperado = _normalizar_valor_estado(sinal.get("depois"))
        antes = _normalizar_valor_estado(sinal.get("antes"))
        if not atributo or esperado == "" or esperado == antes:
            return None

        linhas = [
            linha for linha in _linhas_controle(pagina)
            if _controle_corresponde_linha(linha, controle)
        ]
        if not linhas or len(linhas) > 1:
            return None

        observado = _estado_controle_na_linha(linhas[0], atributo)
        if observado is None:
            return None
        return observado == esperado

    if tipo == "pagina":
        alvo = str(sinal.get("alvo") or "").strip()
        try:
            esperado = int(sinal.get("depois"))
        except (TypeError, ValueError):
            return None
        if alvo not in {"dialogos", "menus", "listboxes"}:
            return None

        marcador = "Elementos flutuantes visiveis:"
        linha = next(
            (
                linha.strip()
                for linha in str(pagina or "").splitlines()
                if marcador in linha
            ),
            None,
        )
        if not linha:
            return None

        prefixo = f"{alvo}="
        valor_texto = None
        for parte in linha.split("|"):
            parte = parte.strip()
            if parte.startswith(prefixo):
                valor_texto = parte[len(prefixo):].strip()
                break
        try:
            observado = int(valor_texto)
        except (TypeError, ValueError):
            return None
        return observado == esperado

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
