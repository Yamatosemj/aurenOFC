from __future__ import annotations

from typing import Any, Callable


def _finalizar_resposta_sucesso(
    objetivo: str,
    historico: list[dict[str, str]],
    resposta: Any,
    *,
    apos_tarefa: Callable[[str, list[dict[str, str]]], Any] | None,
    task_id: str,
    salvar_estrategia: Callable[[str, list[dict[str, str]], str, bool], None],
    task_manager: Any,
    registrar_turno: Callable[[str, str], None],
    write_log: Callable[..., None],
    criar_resposta: Callable[[str], Any],
) -> Any:
    extra = None
    if apos_tarefa is not None and historico:
        try:
            extra = apos_tarefa(objetivo, historico)
        except Exception as erro:
            write_log(
                "MEMORY_ERROR",
                task_id=task_id,
                erro=str(erro),
            )

    if extra:
        texto_final = getattr(resposta, "output_text", "") or ""
        resposta = criar_resposta(texto_final + str(extra))

    final_texto = str(getattr(resposta, "output_text", "") or "").strip()
    salvar_estrategia(
        objetivo,
        historico,
        final_texto,
        True,
    )
    task_manager.complete(
        final_texto,
        task_id=task_id,
    )
    registrar_turno("assistant", final_texto)

    snapshot = task_manager.current_snapshot()
    write_log(
        "TASK_STATE",
        task_id=task_id,
        estado=snapshot.state.value if snapshot else "completed",
    )
    return resposta



def _mensagem_conclusao_local(
    objetivo: str,
    ferramenta: str,
    resultado: str | None = None,
    *,
    terminal_result_tools: set[str],
    multietapa_browser: bool,
) -> str:
    if ferramenta == "listar_abas" and multietapa_browser and resultado:
        return "Concluído: as abas solicitadas foram abertas e verificadas com sucesso."
    if ferramenta in terminal_result_tools and resultado:
        return str(resultado)

    mensagens = {
        "clicar_elemento": "Concluído: executei o clique solicitado com sucesso.",
        "preencher_elemento": "Concluído: preenchi o campo solicitado com sucesso.",
        "pressionar_tecla": "Concluído: pressionei a tecla solicitada com sucesso.",
        "voltar_pagina": "Concluído: voltei uma página.",
        "avancar_pagina": "Concluído: avancei uma página.",
        "recarregar_pagina": "Concluído: recarreguei a página.",
        "rolar_pagina": "Concluído: rolei a página conforme solicitado.",
    }
    return mensagens.get(
        ferramenta,
        "Concluído: a última ação solicitada foi executada com sucesso.",
    )
