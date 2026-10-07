import core.harness as harness_module


def test_harness_execution_cycle_is_delegated_to_dedicated_module(monkeypatch):
    marcador = object()

    def fake_executar_ciclo(harness, objetivo, **kwargs):
        assert objetivo == "teste"
        assert harness is not None
        assert kwargs["executar_rodada_modelo"] is harness_module._executar_rodada_modelo_impl
        assert kwargs["resposta_wrapper"] is harness_module._RespostaWrapper
        return marcador

    monkeypatch.setattr(harness_module, "executar_ciclo", fake_executar_ciclo)

    resultado = harness_module.AurenHarness._executar_ciclo(object(), "teste")
    assert resultado is marcador
