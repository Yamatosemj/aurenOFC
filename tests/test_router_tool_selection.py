import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.router import Router
from core.tools_registry import tools


def names_for(text):
    return Router().select_tool_names(text, tools)


def test_audio_is_subset_and_contains_required_tools():
    names = names_for("coloque o volume em 37%")
    assert "definir_volume_windows" in names
    assert "obter_audio_windows" in names
    assert len(names) < len(tools)


def test_browser_multitab_keeps_browser_controls():
    names = names_for("abra duas abas, Discord e YouTube")
    required = {"listar_abas", "abrir_nova_aba", "trocar_aba", "navegar_navegador"}
    assert required <= set(names)
    assert len(names) < len(tools)


def test_windows_window_task_keeps_window_controls():
    names = names_for("maximize o Bloco de notas")
    assert "maximizar_janela_windows" in names
    assert "listar_janelas_windows" in names
    assert len(names) < len(tools)


def test_system_status_can_use_smallest_specialized_route():
    names = names_for("qual a hora agora?")
    assert names == [
        "consultar_memoria_persistente",
        "listar_janelas_windows",
        "obter_status_windows",
    ]


def test_ambiguous_request_keeps_full_registry():
    names = names_for("faça isso")
    assert names == [item["name"] for item in tools]


def test_uia_checkbox_phrase_keeps_toggle_tool():
    names = names_for("marque a caixa Check Auren Teste da janela AUREN_UIA_TESTE_X")
    assert "alternar_elemento_windows" in names
    assert "clicar_elemento_windows" in names
    assert "preencher_elemento_windows" in names
    assert "selecionar_elemento_windows" in names
    assert len(names) < len(tools)


def test_uia_inspection_phrase_includes_inspector_tool():
    names = names_for("inspecione a interface da janela AUREN_UIA_TESTE procurando Campo de Teste")
    assert "inspecionar_interface_windows" in names
    assert "clicar_elemento_windows" in names
    assert "preencher_elemento_windows" in names
    assert "alternar_elemento_windows" in names
    assert "selecionar_elemento_windows" in names



def test_spotify_play_request_uses_desktop_toolset():
    names = names_for("toque a musica Evidencias no Spotify")
    assert "abrir_programa" in names
    assert "inspecionar_interface_windows" in names
    assert "preencher_elemento_windows" in names
    assert "clicar_elemento_windows" in names
    assert "controle_midia_windows" in names
    assert "navegar_navegador" not in names
    assert len(names) < len(tools)
