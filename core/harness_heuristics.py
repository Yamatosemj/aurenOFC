"""Heurísticas determinísticas usadas pelo Harness para guards locais."""
from __future__ import annotations

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

