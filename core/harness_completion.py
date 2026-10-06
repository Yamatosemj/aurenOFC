from __future__ import annotations


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
