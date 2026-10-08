from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any


def criar_resumo_sessao(store: Any, chat_id: str, limite_turnos: int = 8) -> str:
    """Cria uma frase curta a partir dos turnos persistidos da Tarefa 5.
    O resumo é determinístico e não chama o modelo, evitando custo e latência na saída.
    Custo: uma leitura SQLite e processamento linear dos turnos."""
    if store is None or not chat_id:
        return ""
    rows = store.ultimas_conversas(chat_id, limite=limite_turnos).get("resultados") or []
    objetivos = [
        " ".join(str(item.get("conteudo", "")).split())
        for item in rows
        if item.get("papel") == "user" and str(item.get("conteudo", "")).strip()
    ]
    if not objetivos:
        return ""
    partes = []
    for objetivo in objetivos[-3:]:
        partes.append(objetivo[:177].rstrip() + ("..." if len(objetivo) > 177 else ""))
    if len(partes) == 1:
        return f"Na última sessão, você falou sobre: {partes[0]}"
    return "Na última sessão, você trabalhou em: " + "; ".join(partes)


def preparar_abertura(store: Any) -> str:
    """Consome a lembrança da sessão anterior para uma única abertura.
    O armazenamento marca o registro como consumido antes de devolvê-lo ao chamador.
    Custo: uma leitura e uma escrita SQLite local."""
    entry = store.consumir_ultimo_resumo_sessao() if store is not None else None
    if not entry:
        return ""
    return " ".join(str(entry.get("resumo", "")).split())[:360]


def salvar_fechamento(store: Any, chat_id: str, resumo: str) -> bool:
    """Salva uma frase curta para a próxima inicialização do Auren.
    Credenciais e segredos continuam bloqueados pelo PersistentMemoryStore.
    Custo: uma escrita SQLite local."""
    if store is None:
        return False
    return bool(store.salvar_resumo_sessao(chat_id, resumo).get("ok"))


def monitoramento_necessario(store: Any) -> bool:
    """Verifica se o monitoramento opcional está ligado e ainda não rodou hoje.
    A decisão é persistente e sobrevive ao reinício do processo.
    Custo: uma leitura SQLite local."""
    return bool(store is not None and store.pode_checar_monitoramento_hoje())


def marcar_monitoramento(store: Any) -> None:
    """Marca a checagem passiva diária como concluída.
    A marcação acontece mesmo quando nenhum tópico gera alerta.
    Custo: uma escrita SQLite local."""
    if store is not None:
        store.marcar_monitoramento_checado()


def chave_alerta(texto: str) -> str:
    """Gera uma chave estável para comparar o conteúdo de um alerta externo.
    A chave impede que a mesma descoberta seja anunciada repetidamente.
    Custo: O(n) no tamanho do texto."""
    return hashlib.sha256(" ".join(str(texto or "").split()).encode("utf-8")).hexdigest()[:16]


def hoje_utc() -> str:
    """Retorna a data UTC usada pela trava diária de monitoramento.
    Centraliza a referência temporal para testes determinísticos.
    Custo: O(1)."""
    return datetime.now(timezone.utc).date().isoformat()


def checar_topicos(store: Any) -> list[str]:
    """Consulta uma vez os tópicos habilitados e devolve alertas curtos.
    A checagem é somente leitura e respeita a trava diária persistente.
    Custo: até uma busca web por tópico configurado."""
    if not monitoramento_necessario(store):
        return []
    topicos = store.listar_topicos_proativos()
    if not topicos:
        marcar_monitoramento(store)
        return []
    from tools.web_search import pesquisar_web
    alertas = []
    for topico in topicos:
        resultado = pesquisar_web(topico, "news")
        if not getattr(resultado, "ok", False):
            continue
        fontes = (getattr(resultado, "data", {}) or {}).get("fontes", [])
        if not fontes:
            continue
        primeiro = fontes[0]
        trecho = " ".join(str(primeiro.get("trecho", "")).split())
        if trecho:
            alertas.append(f"Atualização sobre {topico}: {trecho[:260]}")
    marcar_monitoramento(store)
    return alertas
