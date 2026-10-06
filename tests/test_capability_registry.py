import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.capabilities import CAPABILITY_REGISTRY
from core.capability_resolver import effective_confirmation
from core.tools_registry import tools as TOOL_REGISTRY
from core.router import Router


def base_spec(objective, *, parametros=None, dados_exatos=None, confirmacao=False):
    return {
        "version": "1",
        "tipo": "execucao",
        "objetivo": objective,
        "complexidade": "simples",
        "parametros": parametros or {},
        "restricoes": [],
        "requer_confirmacao": confirmacao,
        "dados_exatos": dados_exatos or {},
    }


def test_registry_only_contains_v43_backed_tools():
    available = {item["name"] for item in TOOL_REGISTRY}
    for capability in CAPABILITY_REGISTRY.all():
        assert capability.tools
        assert set(capability.tools) <= available


def test_registry_contains_real_v44_capabilities_only():
    expected = {
        "abrir_programa",
        "abrir_url",
        "pesquisar_web",
        "interagir_com_browser",
        "gerenciar_abas",
        "tocar_musica_spotify",
        "controlar_janela",
        "controlar_audio",
        "consultar_status_windows",
        "localizar_arquivo",
        "memoria_persistente",
        "analisar_tela",
    }
    assert set(CAPABILITY_REGISTRY.ids()) == expected


def test_open_youtube_resolves_to_known_service_url_and_local():
    result = Router().route_task_spec(base_spec("Abrir o YouTube", dados_exatos={"destino": "YouTube"}))
    assert result.status == "resolved"
    assert result.capability_id == "abrir_url"
    assert result.route == "local"
    assert result.params["url"] == "https://www.youtube.com"


def test_explicit_url_in_parametros_is_accepted():
    result = Router().route_task_spec(
        base_spec(
            "Abrir este link",
            parametros={"url": "https://example.com"},
        )
    )
    assert result.capability_id == "abrir_url"
    assert result.route == "local"
    assert result.params["url"] == "https://example.com"


def test_url_in_dados_exatos_and_not_in_parametros_is_accepted():
    result = Router().route_task_spec(
        base_spec(
            "Abrir este link",
            dados_exatos={"url": "https://example.com/pagina"},
        )
    )
    assert result.capability_id == "abrir_url"
    assert result.params["url"] == "https://example.com/pagina"


def test_program_explicitly_requested_as_app_goes_to_open_program():
    result = Router().route_task_spec(
        base_spec(
            "Abra o Chrome aplicativo",
            dados_exatos={"programa": "Chrome"},
        )
    )
    assert result.capability_id == "abrir_programa"
    assert result.route == "local"
    assert result.params["programa"] == "Chrome"


def test_plain_known_service_does_not_require_program_registry_entry():
    result = Router().route_task_spec(
        base_spec("Abre o TikTok", dados_exatos={"destino": "TikTok"})
    )
    assert result.capability_id == "abrir_url"
    assert result.params["url"] == "https://www.tiktok.com"


def test_unknown_site_becomes_unresolved_instead_of_luna_fallback():
    result = Router().route_task_spec(
        base_spec(
            "Abre aquele site que eu vi ontem",
            dados_exatos={"destino": "aquele site que eu vi ontem"},
        )
    )
    assert result.status == "unresolved"
    assert result.route is None
    assert result.reason_code == "missing_parameters"
    assert result.capability_id == "abrir_url"
    assert result.should_clarify is True


def test_unknown_capability_stops_after_two_clarification_rounds():
    router = Router()
    spec = base_spec(
        "Abre aquele site que eu vi ontem",
        dados_exatos={"destino": "aquele site que eu vi ontem"},
    )
    first = router.route_task_spec(spec, clarification_round=1)
    second = router.route_task_spec(spec, clarification_round=2)
    assert first.should_clarify is True
    assert first.exhausted is False
    assert second.should_clarify is False
    assert second.exhausted is True


def test_multistep_browser_task_goes_to_luna():
    result = Router().route_task_spec(
        base_spec(
            "Abra o YouTube, pesquise Create Aeronautics e abra o primeiro vídeo"
        )
    )
    assert result.status == "resolved"
    assert result.capability_id == "interagir_com_browser"
    assert result.route == "luna"
    assert result.params["objetivo_browser"]


def test_simple_web_search_can_stay_local():
    result = Router().route_task_spec(
        base_spec("Pesquise Create Aeronautics")
    )
    assert result.capability_id == "pesquisar_web"
    assert result.route == "local"
    assert result.params["consulta"] == "Create Aeronautics"


def test_browser_tabs_are_local_and_deterministic():
    result = Router().route_task_spec(
        base_spec("Abra duas abas novas", parametros={"acao": "abrir", "quantidade": 2})
    )
    assert result.capability_id == "gerenciar_abas"
    assert result.route == "local"
    assert result.params["quantidade"] == 2


def test_window_action_is_local():
    result = Router().route_task_spec(
        base_spec("Maximize a janela do Bloco de Notas", parametros={"acao": "maximizar", "janela": "Bloco de Notas"})
    )
    assert result.capability_id == "controlar_janela"
    assert result.route == "local"


def test_audio_action_is_local():
    result = Router().route_task_spec(
        base_spec("Coloque o volume em 37%", parametros={"acao": "volume", "percentual": 37})
    )
    assert result.capability_id == "controlar_audio"
    assert result.route == "local"


def test_status_query_is_local():
    result = Router().route_task_spec(base_spec("Qual a hora agora?"))
    assert result.capability_id == "consultar_status_windows"
    assert result.route == "local"


def test_file_search_is_local():
    result = Router().route_task_spec(
        base_spec("Encontre o PDF da aula", dados_exatos={"consulta": "PDF da aula"})
    )
    assert result.capability_id == "localizar_arquivo"
    assert result.route == "local"
    assert result.params["consulta"] == "PDF da aula"


def test_memory_operation_is_local():
    result = Router().route_task_spec(
        base_spec(
            "Guarde isso na memória",
            parametros={"acao": "salvar", "chave": "preferencia", "valor": "lofi"},
        )
    )
    assert result.capability_id == "memoria_persistente"
    assert result.route == "local"


def test_confirmation_policy_never_overrides_true_model_signal():
    result = Router().route_task_spec(
        base_spec("Abrir o YouTube", dados_exatos={"destino": "YouTube"}, confirmacao=True)
    )
    assert result.capability_id == "abrir_url"
    assert result.requer_confirmacao_efetiva is False


def test_core_policy_preserves_model_signal_for_non_forced_capability():
    capability = CAPABILITY_REGISTRY.get("interagir_com_browser")
    assert capability is not None
    assert effective_confirmation(True, capability) is True
    assert effective_confirmation(False, capability) is False


def test_capability_resolution_accepts_value_in_either_parameter_container():
    router = Router()
    via_parametros = router.route_task_spec(
        base_spec("Abrir este link", parametros={"url": "https://example.com"})
    )
    via_dados = router.route_task_spec(
        base_spec("Abrir este link", dados_exatos={"url": "https://example.com"})
    )
    assert via_parametros.capability_id == "abrir_url"
    assert via_dados.capability_id == "abrir_url"
    assert via_parametros.params["url"] == via_dados.params["url"]


def test_dados_exatos_wins_when_same_field_exists_in_both_containers():
    result = Router().route_task_spec(
        base_spec(
            "Abrir este link",
            parametros={"url": "https://nao-e-esta.example"},
            dados_exatos={"url": "https://example.com/exato"},
        )
    )
    assert result.capability_id == "abrir_url"
    assert result.params["url"] == "https://example.com/exato"


def test_complexity_field_does_not_choose_route():
    simple = Router().route_task_spec(
        base_spec(
            "Abra o YouTube, pesquise Create Aeronautics e abra o primeiro vídeo",
            dados_exatos={"destino": "YouTube"},
            confirmacao=False,
        )
    )
    complex_ = Router().route_task_spec(
        base_spec(
            "Abra o YouTube, pesquise Create Aeronautics e abra o primeiro vídeo",
            dados_exatos={"destino": "YouTube"},
        ) | {"complexidade": "complexa"}
    )
    assert simple.route == complex_.route == "luna"


def test_spotify_music_request_resolves_to_luna_desktop_capability():
    result = Router().route_task_spec(
        base_spec("Toque a musica Evidencias no Spotify")
    )
    assert result.status == "resolved"
    assert result.capability_id == "tocar_musica_spotify"
    assert result.route == "luna"
    assert result.params["consulta"] == "Evidencias"


def test_spotify_is_known_service():
    result = Router().route_task_spec(
        base_spec("Abra o Spotify", dados_exatos={"destino": "Spotify"})
    )
    assert result.capability_id == "abrir_url"
    assert result.route == "local"
    assert result.params["url"] == "https://open.spotify.com"


def test_spotify_prefix_request_resolves():
    result = Router().route_task_spec(
        base_spec("Spotify, toque Evidencias")
    )
    assert result.status == "resolved"
    assert result.capability_id == "tocar_musica_spotify"
    assert result.route == "luna"
    assert result.params["consulta"] == "Evidencias"
