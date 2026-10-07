import inspect

from core import harness
from core import harness_cycle


def test_harness_cycle_is_reexported_as_the_execution_owner():
    assert harness._executar_ciclo_impl is harness_cycle.executar_ciclo
    assert harness._executar_ciclo_impl.__module__ == "core.harness_cycle"


def test_harness_cycle_facade_preserves_the_harness_method_contract():
    method = harness.AurenHarness._executar_ciclo
    source = inspect.getsource(method)
    assert "return _executar_ciclo_impl(self, objetivo, _RespostaWrapper, _write_log)" in source



def test_browser_guard_reset_requires_positive_verifier_evidence():
    verifier = harness_cycle._browser_verification_concluida

    assert verifier([{"ferramenta": "obter_contexto_navegador", "sucesso": True, "verificacao_browser": True}]) is True
    assert verifier([{"ferramenta": "obter_contexto_navegador", "sucesso": True, "verificacao_browser": False}]) is False
    assert verifier([{"ferramenta": "obter_contexto_navegador", "sucesso": True, "verificacao_browser": None}]) is False
