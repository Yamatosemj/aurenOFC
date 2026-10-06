from __future__ import annotations

from core.router import Router
from core.capability_resolver import CapabilityResolver
from core.intent_resolver import IntentResolver


def main() -> None:
    phrase = "toque a musica Evidencias no Spotify"
    router = Router()
    all_tools = [{"name": name} for name in [
        "abrir_programa", "listar_janelas_windows", "focar_janela_windows",
        "inspecionar_interface_windows", "clicar_elemento_windows",
        "preencher_elemento_windows", "pressionar_tecla_windows",
        "controle_midia_windows", "navegar_navegador", "ler_pagina",
    ]]
    selected = router.select_tool_names(phrase, all_tools)
    resolution = CapabilityResolver().resolve({
        "version": "1", "tipo": "execucao", "objetivo": phrase,
        "complexidade": "complexa", "parametros": {}, "restricoes": [],
        "requer_confirmacao": False, "dados_exatos": {},
    })
    print({
        "router_domains": router.last_domains,
        "router_tools": selected,
        "capability_id": resolution.capability_id,
        "route": resolution.route,
        "params": resolution.params,
    })


if __name__ == "__main__":
    main()
