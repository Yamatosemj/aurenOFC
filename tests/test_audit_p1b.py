import json
from types import SimpleNamespace

from core.harness_guards import _tratar_rodada_sem_ferramentas
from core.harness_multitab import _multitab_concluida
from core.harness_serialization import _texto_seguro
from core.harness_tools import _executar_chamadas_rodada
from core.tool_result import ToolResult
from tests.test_harness_tools import _TaskManager, _item
from tests.test_harness_loop_owner import _Bench, _resp, _call


def test_aud005_exhausted_multitab_is_failure():
    result = _tratar_rodada_sem_ferramentas(
        objetivo="abra https://example.invalid na primeira aba", historico=[], rodada=3,
        exigir_ferramenta=False, ferramentas_executadas=1, resposta=SimpleNamespace(output_text="feito"),
        vision_reobserve_pending=False, vision_guard_attempts=0, multitab_guard_attempts=2,
        task_id="ficticio", task_manager=_TaskManager(), montar_estado=lambda *a: "",
        pedir_modelo=lambda *a: None, log_resposta_modelo=lambda *a, **kw: None,
        parece_tarefa_multietapa_browser=lambda _: True, extrair_destinos_abas=lambda _: {1: "https://example.invalid"},
        multitab_concluida=lambda *a: False, write_log=lambda *a, **kw: None)
    assert result.acao == "falhar"


def test_aud006_host_prefix_is_not_expected_destination():
    assert not _multitab_concluida("abra https://github.com na primeira aba", [{
        "ferramenta": "listar_abas", "resultado": "Aba 1: Ficticia | https://github.com.evil.invalid"}])


def test_aud007_off_and_reactivate_release_visual_busy():
    from interface_auren import AurenDesktop
    app = object.__new__(AurenDesktop)
    app.mode, app.busy, app.closing = "active", True, False
    app.worker = SimpleNamespace(go_off=lambda: None, activate=lambda: None)
    app._dismiss_confirmation = lambda: None
    app._update_mode = lambda: None
    app.set_mode("off")
    app.set_mode("active")
    assert not app.busy


def test_aud009_no_discarded_model_call_after_last_round():
    bench = _Bench(lambda n, _: _resp([_call(n, "ler_pagina")]), max_rounds=1)
    bench.harness._pode_encerrar_localmente = lambda *a, **kw: False
    bench.run("leia a pagina")
    assert bench.model_calls == 1


def test_aud012_bounded_file_output_preserves_json_and_correct_cursor():
    output = ToolResult.success("lido", data={"file_content": {
        "conteudo": "A" * 5000, "inicio": 40, "truncado": False, "proximo_inicio": None},
        "proxima_leitura": None}).for_model()
    compact = _texto_seguro(output, 2200)
    parsed = json.loads(compact)
    assert len(compact) <= 2200
    content = parsed["dados"]["file_content"]
    assert content["truncado"] is True
    assert content["proximo_inicio"] == 40 + len(content["conteudo"])
    assert parsed["dados"]["proxima_leitura"]["inicio"] == content["proximo_inicio"]


def test_liv004_context_without_action_does_not_arm_verification():
    state = {"pending": False}
    _executar_chamadas_rodada([_item("obter_contexto_navegador", "a")],
        historico=[], task_manager=_TaskManager(), task_id="ficticio", rodada=1,
        executar_ferramenta=lambda _: ToolResult.success("contexto"), trace=None,
        vision_state_mutating_tools=set(), vision_reobserve_pending=False, falha_nao_recuperada=False,
        max_tool_result_chars=2200, get_active_vision_geometry=lambda: None,
        clear_active_vision_geometry=lambda: None, write_log=lambda *a, **kw: None,
        browser_verification_state=state, browser_verifier=lambda *a: None)
    assert state["pending"] is False


def test_aud026_observation_without_proof_does_not_reset_counter():
    bench = _Bench(lambda n, _: _resp([_call(n, "obter_contexto_navegador")]), max_rounds=1)
    h = bench.harness
    h._parece_tarefa_browser_verificavel = lambda *a, **kw: True
    h._pode_encerrar_localmente = lambda *a, **kw: False
    h._browser_verification_guard_attempts = 2
    # Inicializacao da tarefa normalmente limpa o contador; exercitar o ciclo com estado pendente.
    from core.harness_cycle import executar_ciclo
    from core.harness import _RespostaWrapper
    h._task_id = h.task_manager.create("ficticio").task_id
    h.task_manager.start(h._task_id)
    h._browser_verification_pending = True
    h._browser_verification_state = {"pending": True, "ferramenta": "preencher_elemento", "argumentos": "{}"}
    executar_ciclo(h, "ficticio", _RespostaWrapper, lambda *a, **kw: None)
    assert h._browser_verification_guard_attempts == 2


def test_aud030_refresh_preserves_second_control(tmp_path):
    import base64
    import subprocess
    from tools.windows_uia import _UI_AUTOMATION_POWERSHELL as source
    start = source.index("                    $freshRoot =")
    end = source.index("                } catch {", start)
    helper = ""
    if "function Resolve-AuthorizedControl" in source:
        begin = source.index("function Resolve-AuthorizedControl")
        helper = source[begin:source.index("\nfunction ", begin + 1)]
    setup = r"""
Add-Type -AssemblyName UIAutomationClient
function New-Control($id) {
    $element = [pscustomobject]@{ Id=$id }
    $element | Add-Member ScriptMethod GetRuntimeId { @([int]$this.Id) }
    $element | Add-Member ScriptMethod GetCurrentPattern { param($ignored) [pscustomobject]@{Current=[pscustomobject]@{Value=$this.Id}} }
    [pscustomobject]@{Element=$element;IsPassword=$false;Enabled=$true;Offscreen=$false}
}
$first=New-Control 1
$second=New-Control 2
$item=$second
$indice=2
$authorizedRuntimeId='2'
$authorizedPassword=$false
$target='ficticio'
$payload=[pscustomobject]@{hwnd='42'}
function Get-RootElement($ignored) { 'fake' }
function Get-AllControls($ignored) { 'fake' }
function Find-Controls($a,$b,$c) { @([pscustomobject]@{Item=$first},[pscustomobject]@{Item=$second}) }
function Safe-String($value) { [string]$value }
"""
    script = setup + helper + source[start:end] + "\nif ($item.Element.Id -ne 2) { throw 'Controle errado' }; 'SEGUNDO_OK'"
    proc = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand",
                           base64.b64encode(script.encode("utf-16-le")).decode()],
                          capture_output=True, text=True, timeout=15, cwd=tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "SEGUNDO_OK" in proc.stdout
