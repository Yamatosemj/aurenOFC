from __future__ import annotations

from tools import applications


def test_find_application_rejects_tied_fuzzy_match(monkeypatch):
    monkeypatch.setattr(
        applications,
        "buscar_aplicativos_do_windows",
        lambda: [
            {"Name": "Editor Pro", "AppID": "app.editor.pro"},
            {"Name": "Editor Plus", "AppID": "app.editor.plus"},
        ],
    )

    assert applications.encontrar_aplicativo("Editor") is None


def test_find_application_keeps_exact_match_ahead_of_fuzzy_tie(monkeypatch):
    monkeypatch.setattr(
        applications,
        "buscar_aplicativos_do_windows",
        lambda: [
            {"Name": "Editor Pro", "AppID": "app.editor.pro"},
            {"Name": "Editor Plus", "AppID": "app.editor.plus"},
            {"Name": "Editor", "AppID": "app.editor"},
        ],
    )

    result = applications.encontrar_aplicativo("Editor")
    assert result == {"Name": "Editor", "AppID": "app.editor"}
