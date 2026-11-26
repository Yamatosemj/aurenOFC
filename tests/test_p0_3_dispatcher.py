import tools.dispatcher as dispatcher


def test_normal_field_keeps_original_target():
    import tools.dispatcher as d
    from unittest.mock import patch

    identity = {"hwnd": 100, "runtime_id": "1:2:3", "nome": "Campo de Teste", "automation_id": "Campo", "tipo": "Edit", "protegido": False}
    with patch.object(d.windows, "preencher_elemento_windows", return_value="ok") as mock_fill:
        result = d._preencher_windows_handler({"alvo_janela": "janela", "alvo": "Campo de Teste", "texto": "abc", "indice": 1}, None, {"uia_protected": False, "uia_resolved_name": "Campo de Teste", "uia_resolved_id": "Campo", "uia_expected_identity": identity})
    assert result == "ok"
    mock_fill.assert_called_once_with("janela", "Campo de Teste", "abc", 1, False, identity)


def test_protected_field_reuses_resolved_identity():
    import tools.dispatcher as d
    from unittest.mock import patch

    identity = {"hwnd": 100, "runtime_id": "1:2:3", "nome": "Senha de Teste", "automation_id": "Senha", "tipo": "Edit", "protegido": True}
    with patch.object(d.windows, "preencher_elemento_windows", return_value="ok") as mock_fill:
        result = d._preencher_windows_handler({"alvo_janela": "janela", "alvo": "Senha de Teste", "texto": "abc", "indice": 1}, None, {"uia_protected": True, "uia_resolved_name": "Senha de Teste", "uia_resolved_id": "Senha", "uia_expected_identity": identity})
    assert result == "ok"
    mock_fill.assert_called_once_with("janela", "Senha", "abc", 1, True, identity)
