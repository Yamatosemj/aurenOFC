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
