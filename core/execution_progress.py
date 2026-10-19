"""Observational execution events scoped to the worker context, never authority."""
from contextvars import ContextVar

observer = ContextVar("auren_execution_progress", default=None)
LABELS = {
    "context": "Preparando o contexto da conversa…",
    "model": "Consultando a IA…",
    "intent": "Verificando a ação proposta…",
    "tool": "Executando a ferramenta autorizada…",
    "verification": "Verificando o resultado…",
}

def emit(stage):
    callback = observer.get()
    if callback is not None and stage in LABELS:
        try:
            callback(LABELS[stage])
        except Exception:
            pass  # Presentation can never change execution or permissions.
