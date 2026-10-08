from __future__ import annotations

from typing import Any


def ativar(store: Any, ativo: bool) -> dict[str, Any]:
    """Altera explicitamente o estado do monitoramento proativo.
    O estado é persistente e desligado por padrão até o usuário ativá-lo.
    Custo: uma escrita SQLite local."""
    return store.definir_monitoramento_proativo(bool(ativo))


def status(store: Any) -> dict[str, Any]:
    """Retorna o estado do monitoramento sem consultar a internet.
    Serve como fonte única para a interface de configuração.
    Custo: uma leitura SQLite local."""
    estado = store.obter_monitoramento_proativo()
    estado["topicos"] = store.listar_topicos_proativos()
    return estado


def adicionar(store: Any, topico: str) -> dict[str, Any]:
    """Adiciona um tópico à lista passiva sem iniciar consultas.
    A inclusão não liga o recurso global.
    Custo: uma escrita SQLite local."""
    return store.adicionar_topico_proativo(topico)


def remover(store: Any, topico: str) -> dict[str, Any]:
    """Remove um tópico da lista passiva sem alterar o estado global.
    Nenhuma consulta externa é feita.
    Custo: uma escrita SQLite local."""
    return store.remover_topico_proativo(topico)
