from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from core.capabilities import CAPABILITY_REGISTRY, KNOWN_SERVICES
from core.utils import normalizar_nome


@dataclass(frozen=True)
class ResolvedIntent:
    capability_id: str | None
    params: dict[str, Any]
    reason_code: str
    reason: str

    @property
    def resolved(self) -> bool:
        return self.capability_id is not None


def _merged_fields(task_spec: Mapping[str, Any]) -> dict[str, Any]:
    parametros = task_spec.get("parametros")
    dados_exatos = task_spec.get("dados_exatos")

    merged: dict[str, Any] = {}
    if isinstance(parametros, Mapping):
        merged.update(parametros)
    if isinstance(dados_exatos, Mapping):
        # Dados exatos ganham se o mesmo campo aparecer nos dois lugares.
        merged.update(dados_exatos)
    return merged


def _field(data: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in data and data[name] not in (None, ""):
            return data[name]
    return None


def _objective(task_spec: Mapping[str, Any]) -> str:
    return str(task_spec.get("objetivo") or "").strip()


def _normalized_objective(task_spec: Mapping[str, Any]) -> str:
    return normalizar_nome(_objective(task_spec))


def _find_url(text: str) -> str | None:
    match = re.search(r"https?://[^\s<>]+", text, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(0).rstrip(".,);]")


def _known_service_url(value: Any) -> str | None:
    if not value:
        return None
    normalized = normalizar_nome(str(value))
    return KNOWN_SERVICES.get(normalized)


def _is_explicit_app_request(objective: str) -> bool:
    normalized = normalizar_nome(objective)
    return bool(
        re.search(r"\b(aplicativo|app|programa|software)\b", normalized)
    )


def _opening_verb(objective: str) -> bool:
    normalized = normalizar_nome(objective)
    return bool(
        re.search(
            r"\b(abrir|abre|abra|iniciar|inicie|executar|execute|rodar|rode)\b",
            normalized,
        )
    )


def _extract_after_opening_verb(objective: str) -> str | None:
    match = re.search(
        r"\b(?:abrir|abre|abra|iniciar|inicie|executar|execute|rodar|rode)\b\s+(?:(?:o|a|um|uma)\s+)?(.+)$",
        objective.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    candidate = match.group(1).strip()
    candidate = re.sub(
        r"\s+(?:agora|por favor|pra mim|para mim)$",
        "",
        candidate,
        flags=re.IGNORECASE,
    ).strip(" .!?\t")
    return candidate or None


def _looks_like_browser_multistep(objective: str) -> bool:
    normalized = normalizar_nome(objective)
    if re.search(r"\bclique\b|\bpreench", normalized):
        return True
    if re.search(r"\b(assista|veja)\b", normalized):
        return True
    if re.search(r"\b(primeiro|segundo|terceiro|resultado|video)\b", normalized) and re.search(
        r"\b(pesquis\w*|busc\w*|procur\w*|abrir|encontr\w*)\b",
        normalized,
    ):
        return True
    return bool(
        re.search(r"\b(e|depois)\b", normalized)
        and re.search(r"\b(pesquisar|buscar|procurar|abrir|clicar|preencher)\b", normalized)
        and re.search(r"\b(youtube|site|pagina|video|link|resultado)\b", normalized)
    )


def _extract_search_query(objective: str) -> str | None:
    match = re.search(
        r"\b(?:pesquisar|pesquise|pesquisa|buscar|busque|busca|procurar|procure|procura)\b\s+(?:por\s+)?(.+)$",
        objective.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    candidate = match.group(1).strip().strip(" .!?\t")
    candidate = re.split(r"\s+e\s+(?:abra|abrir|clique|veja|assista)\b", candidate, maxsplit=1, flags=re.IGNORECASE)[0]
    return candidate.strip() or None


def _extract_audio_action(objective: str) -> tuple[str | None, int | None]:
    normalized = normalizar_nome(objective)

    volume_match = re.search(r"\b(?:volume|som|audio)\b[^\d]{0,18}\b(?:em|para|pra|deixe|deixa|coloque|coloca|a)?\s*(\d{1,3})\s*%?\b", normalized)
    if volume_match:
        percentual = int(volume_match.group(1))
        if 0 <= percentual <= 100:
            return "volume", percentual

    if re.search(r"\b(tira|tirar|desativa|desative|desativar|remove|remover)\b.*\bmudo\b", normalized):
        return "mudo_off", None
    if re.search(r"\b(mudo|silencia|silencie|silenciar|mutar|mute)\b", normalized):
        return "mudo", None
    if re.search(r"\b(pausa|pause|parar|pare|play\s*/?\s*pause)\b", normalized):
        return "play_pause", None
    if re.search(r"\b(proxima|proximo)\b.*\bmusica\b|\bproxima musica\b", normalized):
        return "proxima", None
    if re.search(r"\banterior\b.*\bmusica\b|\bmusica anterior\b", normalized):
        return "anterior", None
    if re.search(r"\b(qual|como)\b.*\b(volume|som|audio)\b", normalized):
        return "consultar", None
    return None, None


def _best_pattern_match(normalized_objective: str) -> str | None:
    candidatos: list[tuple[int, int, str]] = []
    for capability in CAPABILITY_REGISTRY.all():
        for pattern in capability.padroes_objetivo:
            if re.search(pattern, normalized_objective, flags=re.IGNORECASE):
                candidatos.append((capability.prioridade, -len(pattern), capability.id))
                break

    if not candidatos:
        return None
    candidatos.sort()
    return candidatos[0][2]


class IntentResolver:
    """Transforma TaskSpec em uma intencao interna explicita.

    Nao escolhe local vs. Luna. Apenas determina qual capacidade o Core acredita
    que o TaskSpec representa e extrai parametros necessarios sem depender de
    uma chamada adicional a modelo.
    """

    def resolve(self, task_spec: Mapping[str, Any]) -> ResolvedIntent:
        if task_spec.get("tipo") != "execucao":
            return ResolvedIntent(
                capability_id=None,
                params={},
                reason_code="not_execution",
                reason="TaskSpec nao representa uma execucao.",
            )

        objective = _objective(task_spec)
        normalized = _normalized_objective(task_spec)
        data = _merged_fields(task_spec)

        # 0) Tocar musica/playlist no Spotify e uma tarefa web especifica.
        if (
            re.search(r"\bspotify\b", normalized)
            and re.search(r"\b(?:toc(?:ar|a)|toqu(?:e|em)|reproduz(?:ir|a)|execute|executa)\b", normalized)
        ):
            consulta = _field(data, "consulta", "musica", "m[uú]sica", "playlist", "titulo", "título")
            if consulta is None:
                # Remove o servico e o verbo, preservando o titulo/playlist pedido.
                consulta = re.sub(r"\b(?:toc(?:ar|a)|toqu(?:e|em)|reproduz(?:ir|a)|execute|executa)\b", " ", objective, flags=re.IGNORECASE)
                consulta = re.sub(r"\b(?:no|na|em|pelo|pela)\s+spotify\b", " ", consulta, flags=re.IGNORECASE)
                consulta = re.sub(r"\bspotify\b", " ", consulta, flags=re.IGNORECASE)
                consulta = re.sub(r"\b(?:a|o|um|uma)\s+(?:m[uú]sica|playlist|faixa)\b", " ", consulta, flags=re.IGNORECASE)
                consulta = " ".join(consulta.split()).strip(" ,.!?")
            if consulta:
                return ResolvedIntent(
                    capability_id="tocar_musica_spotify",
                    params={"consulta": str(consulta).strip()},
                    reason_code="matched_spotify_playback",
                    reason="Pedido explicito para pesquisar e reproduzir conteudo no Spotify.",
                )

        # 1) Interacao de browser tem prioridade quando a frase ja descreve
        # varias etapas ou interpretacao de pagina.
        if _looks_like_browser_multistep(objective):
            return ResolvedIntent(
                capability_id="interagir_com_browser",
                params={
                    "objetivo_browser": objective,
                    **({"url_inicial": data["url"]} if data.get("url") else {}),
                },
                reason_code="matched_multistep_browser",
                reason="Objetivo exige multiplas etapas ou interpretacao de pagina.",
            )

        # 2) URL explicita ou servico conhecido.
        url = _field(data, "url", "URL", "link") or _find_url(objective)
        destino = _field(data, "destino", "site", "servico", "serviço")
        known_url = url or _known_service_url(destino)
        if known_url is None:
            candidate = _extract_after_opening_verb(objective) if _opening_verb(objective) else None
            if candidate and not _is_explicit_app_request(objective):
                known_url = _known_service_url(candidate)
                if known_url:
                    destino = candidate

        if known_url and _opening_verb(objective):
            params = {"url": known_url}
            if data.get("modo"):
                params["modo"] = data["modo"]
            if data.get("nova_aba") is not None:
                params["nova_aba"] = data["nova_aba"]
            return ResolvedIntent(
                capability_id="abrir_url",
                params=params,
                reason_code="matched_url_or_known_service",
                reason="URL explicita ou servico conhecido resolvido pelo Core.",
            )

        # 3) Abas do navegador.
        if re.search(r"\baba(s)?\b", normalized):
            acao = _field(data, "acao", "ação", "operacao", "operação")
            if not acao:
                if re.search(r"\b(fechar|fecha)\b", normalized):
                    acao = "fechar"
                elif re.search(r"\b(trocar|mudar|ir para)\b", normalized):
                    acao = "trocar"
                elif re.search(r"\b(abrir|abra|abre|nova|novas)\b", normalized):
                    acao = "abrir"
                elif re.search(r"\b(listar|mostrar|mostre|quais)\b", normalized):
                    acao = "listar"
            if acao:
                return ResolvedIntent(
                    capability_id="gerenciar_abas",
                    params={
                        "acao": acao,
                        **({"indice": data["indice"]} if data.get("indice") is not None else {}),
                        **({"url": data["url"]} if data.get("url") else {}),
                        **({"quantidade": data["quantidade"]} if data.get("quantidade") is not None else {}),
                    },
                    reason_code="matched_browser_tabs",
                    reason="Objetivo menciona uma operacao explicita sobre abas.",
                )

        # 4) Programa/aplicativo. Um campo estruturado explicito ganha do texto livre.
        programa = _field(data, "programa", "aplicativo", "app", "software")
        if programa:
            return ResolvedIntent(
                capability_id="abrir_programa",
                params={"programa": str(programa).strip()},
                reason_code="matched_program",
                reason="Pedido identifica explicitamente um programa.",
            )

        # 5) A partir daqui, o Registry escolhe a intencao por regras declaradas
        # em cada capability. O Resolver apenas extrai os parametros da intencao.
        capability_id = _best_pattern_match(normalized)

        if capability_id == "abrir_programa" and _opening_verb(objective):
            programa = _extract_after_opening_verb(objective)
            if programa:
                return ResolvedIntent(
                    capability_id="abrir_programa",
                    params={"programa": programa},
                    reason_code="matched_program",
                    reason="Regra do Registry identificou abertura de programa.",
                )

        if capability_id == "abrir_url":
            return ResolvedIntent(
                capability_id="abrir_url",
                params=({"url": url} if url else {}),
                reason_code="matched_url_capability",
                reason="Regra do Registry identificou uma abertura de site/URL; destino ainda pode precisar de esclarecimento.",
            )

        if capability_id == "tocar_musica_spotify":
            consulta = _field(data, "consulta", "musica", "música", "playlist", "titulo", "título")
            if consulta is None:
                consulta = re.sub(r"\b(?:toc(?:ar|a)|toqu(?:e|em)|reproduz(?:ir|a)|execute|executa)\b", " ", objective, flags=re.IGNORECASE)
                consulta = re.sub(r"\b(?:no|na|em|pelo|pela)\s+spotify\b", " ", consulta, flags=re.IGNORECASE)
                consulta = re.sub(r"\bspotify\b", " ", consulta, flags=re.IGNORECASE)
                consulta = re.sub(r"\b(?:a|o|um|uma)\s+(?:m[uú]sica|playlist|faixa)\b", " ", consulta, flags=re.IGNORECASE)
                consulta = " ".join(consulta.split()).strip(" ,.!?")
            if consulta:
                return ResolvedIntent(
                    capability_id="tocar_musica_spotify",
                    params={"consulta": str(consulta).strip()},
                    reason_code="matched_spotify_playback",
                    reason="Regra do Registry identificou reproducao especifica no aplicativo Spotify do Windows.",
                )

        if capability_id == "pesquisar_web":
            consulta = _field(data, "consulta", "query", "pesquisa", "termo") or _extract_search_query(objective)
            if consulta:
                return ResolvedIntent(
                    capability_id="pesquisar_web",
                    params={"consulta": str(consulta).strip()},
                    reason_code="matched_web_search",
                    reason="Regra do Registry identificou uma pesquisa web direta.",
                )

        if capability_id == "controlar_janela":
            acao = _field(data, "acao", "ação", "operacao", "operação")
            if not acao:
                pares = (("maximiz", "maximizar"), ("minimiz", "minimizar"), ("restaur", "restaurar"), ("redimension", "redimensionar"), ("mover", "mover"), ("fechar", "fechar"), ("focar", "focar"))
                for marcador, nome in pares:
                    if marcador in normalized:
                        acao = nome
                        break
            if acao:
                janela = _field(data, "janela", "alvo", "window")
                return ResolvedIntent(
                    capability_id="controlar_janela",
                    params={"acao": acao, **({"janela": janela} if janela else {})},
                    reason_code="matched_windows_window",
                    reason="Regra do Registry identificou uma operacao de janela do Windows.",
                )

        if capability_id == "controlar_audio":
            acao = _field(data, "acao", "ação", "operacao", "operação")
            percentual = _field(data, "percentual", "volume")
            if not acao:
                acao_extraida, percentual_extraido = _extract_audio_action(objective)
                acao = acao_extraida
                if percentual is None:
                    percentual = percentual_extraido
            if acao:
                params = {"acao": acao}
                if percentual is not None:
                    params["percentual"] = percentual
                return ResolvedIntent(
                    capability_id="controlar_audio",
                    params=params,
                    reason_code="matched_audio",
                    reason="Regra do Registry identificou uma operacao de audio/midia.",
                )

        if capability_id == "consultar_status_windows":
            return ResolvedIntent(
                capability_id="consultar_status_windows",
                params={},
                reason_code="matched_windows_status",
                reason="Regra do Registry identificou uma leitura de estado dinamico do Windows.",
            )

        if capability_id == "localizar_arquivo":
            consulta = _field(data, "consulta", "arquivo", "nome_arquivo", "nome")
            if consulta is None and re.search(r"\b(arquivo|pdf|documento|foto|imagem|video|zip)\b", normalized):
                consulta = objective
            if consulta:
                return ResolvedIntent(
                    capability_id="localizar_arquivo",
                    params={"consulta": str(consulta).strip()},
                    reason_code="matched_file_search",
                    reason="Regra do Registry identificou uma busca local por arquivo.",
                )

        if capability_id == "inspecionar_arquivo":
            caminho = _field(data, "caminho", "path", "arquivo", "nome_arquivo", "nome")
            if caminho:
                return ResolvedIntent(
                    capability_id="inspecionar_arquivo",
                    params={
                        "caminho": str(caminho).strip(),
                        "procurar_copias": bool(data.get("procurar_copias", False)),
                        "limite_copias": int(data.get("limite_copias", 5)),
                    },
                    reason_code="matched_file_inspection",
                    reason="Pedido identifica inspecao estruturada do arquivo.",
                )

        if capability_id == "gerenciar_arquivos":
            acao = _field(data, "acao", "ação", "operacao", "operação")
            if not acao:
                for marcador, nome in (
                    ("renome", "renomear"),
                    ("copi", "copiar"),
                    ("mov", "mover"),
                    ("cri", "criar"),
                ):
                    if marcador in normalized:
                        acao = nome
                        break
            if acao:
                params = {"acao": str(acao).strip()}
                for name in ("origem", "destino", "caminho", "novo_nome"):
                    value = _field(data, name)
                    if value is not None:
                        params[name] = value
                return ResolvedIntent(
                    capability_id="gerenciar_arquivos",
                    params=params,
                    reason_code="matched_file_management",
                    reason="Regra do Registry identificou uma operacao de arquivo com alteracao local.",
                )

        if capability_id == "lixeira_arquivo":
            caminho = _field(data, "caminho", "path", "arquivo", "nome_arquivo", "nome")
            if caminho:
                return ResolvedIntent(
                    capability_id="lixeira_arquivo",
                    params={"caminho": str(caminho).strip()},
                    reason_code="matched_file_trash",
                    reason="Regra do Registry identificou envio explicito para a Lixeira.",
                )

        if capability_id == "ler_arquivo":
            caminho = _field(data, "caminho", "path", "arquivo", "nome_arquivo", "nome")
            if caminho:
                return ResolvedIntent(
                    capability_id="ler_arquivo",
                    params={
                        "caminho": str(caminho).strip(),
                        "inicio": int(data.get("inicio", 0)),
                        "limite_caracteres": int(data.get("limite_caracteres", 12000)),
                    },
                    reason_code="matched_file_read",
                    reason="Pedido identifica leitura controlada do conteudo de um arquivo.",
                )

        if capability_id == "memoria_persistente":
            acao = _field(data, "acao", "ação", "operacao", "operação")
            if not acao:
                if re.search(r"\b(esquec|apag)", normalized):
                    acao = "esquecer"
                elif re.search(r"\b(salv|guard|lembr)", normalized):
                    acao = "salvar"
                else:
                    acao = "consultar"
            return ResolvedIntent(
                capability_id="memoria_persistente",
                params={"acao": acao, **{k: v for k, v in data.items() if k in {"chave", "valor", "consulta", "categoria"}}},
                reason_code="matched_memory",
                reason="Regra do Registry identificou uso explicito da memoria persistente.",
            )

        return ResolvedIntent(
            capability_id=None,
            params={},
            reason_code="capability_unresolved",
            reason="Nenhuma capacidade V43 registrada correspondeu ao TaskSpec.",
        )
