"""Heurísticas determinísticas usadas pelo Harness para guards locais."""
from __future__ import annotations

from typing import Callable

import re


def _parece_tarefa_visual_composta(objetivo: str) -> bool:
    """Detecta tarefas visuais que exigem mais de uma observacao/acao."""
    texto = str(objetivo or "").strip().lower()
    if not texto:
        return False

    tem_visao = bool(
        re.search(
            r"\b(?:analise|analisar|veja|ver|olhe|olhar|observe|observar|confira|conferir|localize|localizar)\b.*\b(?:tela|screenshot|captura)\b",
            texto,
            flags=re.IGNORECASE,
        )
    )
    tem_acao_visual = bool(
        re.search(
            r"\b(?:clique|clica|clicar|arraste|arrastar|mova|mover|digite|digitar|pressione|pressionar|selecione|selecionar)\b",
            texto,
            flags=re.IGNORECASE,
        )
    )
    tem_continuacao = bool(
        re.search(
            r"\b(?:depois|em seguida|ent[aã]o|ap[oó]s|posteriormente)\b|\be\s+(?:confirme|verifique|analise|observe|confira)",
            texto,
            flags=re.IGNORECASE,
        )
    )
    return tem_visao and tem_acao_visual and tem_continuacao


def _parece_tarefa_multietapa_browser(objetivo: str) -> bool:
    """Detecta pedidos explicitamente multi-etapa de abas do navegador.

    E um guard local e conservador: serve apenas para impedir que um
    preflight como ``listar_abas`` seja tratado como resultado final.
    """
    texto = str(objetivo or "").strip().lower()
    if not texto or "aba" not in texto:
        return False

    marcadores_de_quantidade = (
        "duas abas", "2 abas", "tres abas", "três abas", "3 abas",
        "segunda aba", "2ª aba", "segunda",
        "terceira aba", "3ª aba", "terceira",
        "quarta aba", "4ª aba", "quarta",
    )
    if not any(marcador in texto for marcador in marcadores_de_quantidade):
        return False

    return any(
        verbo in texto
        for verbo in (
            "abra", "abrir", "abre", "navegue", "navegar",
            "coloque", "deixe", "carregue", "abrindo",
        )
    )


def _pode_encerrar_localmente(
    objetivo: str,
    resultados_rodada: list[dict[str, object]],
    *,
    vision_reobserve_pending: bool = False,
    browser_verification_pending: bool = False,
    visual_mutating_tools: set[str],
    terminal_result_tools: set[str],
    multitab_concluida: Callable[[str, list[dict[str, str]]], bool],
) -> bool:
    """Decide se podemos evitar uma rodada adicional do modelo."""
    if vision_reobserve_pending:
        return False

    if browser_verification_pending:
        return False

    # Tarefas visuais compostas precisam observar o estado novo antes de
    # encerrar. Sem este guard, um clique DOM presente no fim da primeira
    # rodada poderia ser interpretado como a ultima acao e encerrar a tarefa
    # antes da verificacao visual pedida pelo usuario.
    if _parece_tarefa_visual_composta(objetivo):
        if any(
            str(item.get("ferramenta", "")) in visual_mutating_tools
            and item.get("sucesso")
            for item in resultados_rodada
        ):
            return False

    if _parece_tarefa_multietapa_browser(objetivo) and resultados_rodada:
        ultima_listagem = resultados_rodada[-1]
        if (
            ultima_listagem.get("ferramenta") == "listar_abas"
            and ultima_listagem.get("sucesso")
            and multitab_concluida(objetivo, resultados_rodada)
        ):
            return True

    ultima_acao = _ultima_acao_solicitada(objetivo)
    if ultima_acao and resultados_rodada:
        ultimo = resultados_rodada[-1]
        if ultimo["ferramenta"] == ultima_acao:
            # Fonte unica de verdade: ToolResult.ok, ja registrado em "sucesso".
            return all(item.get("sucesso") for item in resultados_rodada)

    # Para consultas ou acoes simples, uma unica ferramenta terminal
    # com ToolResult/retorno de sucesso ja e suficiente. So aceitamos
    # isso quando houve exatamente uma chamada nesta rodada e, no caso
    # de leitura, a mensagem original nao parecia uma tarefa de acao.
    if len(resultados_rodada) != 1:
        return False

    ultimo = resultados_rodada[0]
    if not ultimo.get("sucesso"):
        return False

    ferramenta = str(ultimo.get("ferramenta", ""))
    if ferramenta not in terminal_result_tools:
        return False

    somente_leitura = ferramenta in {
        "obter_audio_windows",
        "obter_status_windows",
        "listar_janelas_windows",
        "listar_processos_windows",
        "obter_geometria_janela_windows",
        "ler_area_transferencia_windows",
        "listar_abas",
        "obter_contexto_navegador",
        "consultar_memoria_persistente",
    }
    if ferramenta == "listar_abas" and _parece_tarefa_multietapa_browser(objetivo):
        return False
    if somente_leitura and _parece_tarefa_de_acao(objetivo):
        return False
    return True


def _parece_tarefa_de_acao(objetivo: str) -> bool:
    """Identifica comandos que claramente pedem uma acao real.

    E um filtro local, barato e conservador: nao chama outra IA para
    decidir se deve usar ferramentas. A exigencia de ferramenta vale
    apenas para a primeira rodada da tarefa.
    """
    texto = str(objetivo or "").strip().lower()
    if not texto:
        return False

    palavras = re.findall(r"[\wÀ-ÿ]+", texto, flags=re.UNICODE)
    while palavras and palavras[0] in {"auren"}:
        palavras.pop(0)
    if not palavras:
        return False

    primeira_palavra = palavras[0]
    verbos_de_acao = {
        "abre", "abrir", "abra",
        "toca", "toque", "tocar",
        "reproduz", "reproduza", "reproduzir",
        "clica", "clicar", "clique",
        "preenche", "preencher",
        "digita", "digitar",
        "pesquisa", "pesquisar",
        "busca", "buscar",
        "navega", "navegar",
        "entra", "entrar",
        "vai", "ir",
        "rola", "rolar",
        "volta", "voltar",
        "avanca", "avançar", "avancar",
        "recarrega", "recarregar",
        "pressiona", "pressionar",
        "fecha", "fechar",
        "define", "definir", "defina",
        "ativa", "ativar", "ative",
        "desativa", "desativar", "desative",
        "muda", "mudar", "mude",
        "ajusta", "ajustar", "ajuste",
        "inspeciona", "inspecionar", "inspecione",
        "procura", "procurar", "procure",
        "localiza", "localizar", "localize",
    }

    return primeira_palavra in verbos_de_acao


def _ultima_acao_solicitada(objetivo: str) -> str | None:
    """Retorna apenas a ultima acao terminal explicitamente pedida.

    A heuristica e conservadora: so considera verbos inteiros que
    correspondem a ferramentas que podem ser o ultimo passo de uma
    tarefa. Verbos intermediarios como "abrir" ou "pesquisar" nao
    encerram a tarefa por conta propria.
    """
    import re

    texto = str(objetivo or "").strip().lower()
    if not texto:
        return None

    padroes = {
        "clicar_elemento": ("clica", "clicar", "clique"),
        "preencher_elemento": (
            "preenche", "preencher", "preencha",
            "digita", "digitar", "digite",
        ),
        "pressionar_tecla": (
            "pressiona", "pressionar", "pressione",
            "aperta", "apertar", "aperte",
        ),
        "voltar_pagina": ("volta", "voltar", "volte"),
        "avancar_pagina": ("avanca", "avançar", "avancar", "avance"),
        "recarregar_pagina": ("recarrega", "recarregar", "recarregue"),
        "rolar_pagina": ("rola", "rolar", "role"),
    }

    palavras = re.findall(r"[\wÀ-ÿ]+", texto, flags=re.UNICODE)
    encontrados: list[tuple[int, str]] = []
    for indice, palavra in enumerate(palavras):
        for ferramenta, verbos in padroes.items():
            if palavra in verbos:
                encontrados.append((indice, ferramenta))

    if not encontrados:
        return None

    return max(encontrados, key=lambda item: item[0])[1]


def _limite_adaptativo(objetivo: str, padrao: int = 12) -> int:
    texto = str(objetivo or "").strip().lower()
    conectores = len(re.findall(r"\b(?:e|depois|em seguida|entao|então|tambem|também)\b", texto))
    comandos = len(re.findall(r"\b(?:abra|abrir|abra|pesquise|pesquisar|clique|preencha|digite|mova|feche|fechar|procure|encontre|resuma|analise|analise)\b", texto))
    if conectores >= 3 or comandos >= 4 or len(texto) > 180:
        return min(18, padrao + 6)
    if conectores >= 1 or comandos >= 2:
        return min(15, padrao + 3)
    return padrao
