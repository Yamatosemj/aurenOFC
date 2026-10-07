import tools.windows as windows
import tools.windows_window as windows_window


def test_windows_window_controls_live_in_dedicated_module():
    public_names = (
        "listar_janelas_windows",
        "focar_janela_windows",
        "minimizar_janela_windows",
        "maximizar_janela_windows",
        "obter_geometria_janela_windows",
        "mover_janela_windows",
        "redimensionar_janela_windows",
        "restaurar_janela_windows",
        "fechar_janela_windows",
    )

    for name in public_names:
        assert getattr(windows, name) is getattr(windows_window, name)
        assert getattr(windows, name).__module__ == "tools.windows_window"


def test_windows_window_module_owns_window_resolution():
    assert windows._encontrar_janela_windows is windows_window._encontrar_janela_windows
    assert windows._processo_da_janela_windows is windows_window._processo_da_janela_windows
    assert windows._encontrar_janela_windows.__module__ == "tools.windows_window"
    assert windows._processo_da_janela_windows.__module__ == "tools.windows_window"



def test_windows_window_internal_compatibility_exports_are_preserved():
    private_names = (
        "_enumerar_janelas_windows",
        "_encontrar_janela_windows_sem_cache",
        "_titulo_atual_da_janela_windows",
        "_WINDOW_TARGET_CACHE",
    )

    for name in private_names:
        assert getattr(windows, name) is getattr(windows_window, name)

    for name in (
        "_enumerar_janelas_windows",
        "_encontrar_janela_windows_sem_cache",
        "_titulo_atual_da_janela_windows",
    ):
        assert getattr(windows, name).__module__ == "tools.windows_window"
