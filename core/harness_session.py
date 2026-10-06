from __future__ import annotations

from typing import Any, Callable


def _garantir_sessao_chat(
    session: Any,
    *,
    criar_sessao: Callable[[], Any],
    definir_sessao_atual: Callable[[Any], Any],
) -> tuple[Any, bool, str]:
    """Garante uma sessão existente, cria uma nova quando necessário e a vincula ao contexto."""
    if session is None:
        session = criar_sessao()
        iniciou_aqui = True
    else:
        iniciou_aqui = False

    definir_sessao_atual(session)
    return session, iniciou_aqui, session.chat_id

def _encerrar_sessao_chat(
    session: Any,
    status: str = "closed",
    *,
    obter_sessao_atual: Callable[[], Any],
    limpar_sessao_atual: Callable[[], Any],
    limpar_estado_harness: Callable[[], Any],
    limpar_redaction: Callable[[], Any],
    write_log: Callable[..., Any],
) -> bool:
    """Fecha uma sessão existente e executa toda a limpeza de estado associada."""
    if session is None:
        return False

    try:
        write_log("CHAT_END", chat_id=session.chat_id, status=status)
    finally:
        if obter_sessao_atual() is session:
            limpar_sessao_atual()
        limpar_estado_harness()
        limpar_redaction()

    return True
