import inspect

from core import harness
from core import harness_cycle


def test_harness_cycle_is_reexported_as_the_execution_owner():
    assert harness._executar_ciclo_impl is harness_cycle.executar_ciclo
    assert harness._executar_ciclo_impl.__module__ == "core.harness_cycle"


def test_harness_cycle_facade_preserves_the_harness_method_contract():
    method = harness.AurenHarness._executar_ciclo
    source = inspect.getsource(method)
    assert "return _executar_ciclo_impl(self, objetivo, _RespostaWrapper)" in source
