"""O diagnostico de bloqueio nao pode autorizar acao nem registrar dados privados."""
from __future__ import annotations

from types import SimpleNamespace

from core.harness_intent_guard import (
    _diagnostico_propostas_bloqueadas,
    verificar_antes_de_agir,
)
from core.intent_verification import IntentDecision


def _call(name, arguments):
    return SimpleNamespace(name=name, arguments=arguments)


def test_diagnostico_limita_argumentos_e_registra_pid_nome_verificavel():
    resultado = _diagnostico_propostas_bloqueadas([
        _call("encerrar_processo_windows", '{"nome":"steamwebhelper.exe","pid":8636}'),
        _call("preencher_elemento", '{"texto":"minha-senha-secreta","selector":"login"}'),
        _call("encerrar_processo_windows", '{"nome":"invalido com espaco","pid":"8636"}'),
    ])
    assert resultado == [
        {"ferramenta": "encerrar_processo_windows", "nome_processo": "steamwebhelper.exe", "pid": 8636},
        {"ferramenta": "preencher_elemento"},
        {"ferramenta": "encerrar_processo_windows"},
    ]
    assert "minha-senha-secreta" not in repr(resultado)


def test_bloqueio_da_steam_registra_diagnostico_e_nao_executa_nada():
    eventos = []
    acoes = [_call("encerrar_processo_windows", '{"nome":"steamservice.exe","pid":10760}')]
    harness = SimpleNamespace(
        _task_id="test-close",
        verificar_intencao=lambda *_: IntentDecision(
            "bloquear", "Nao ha evidencias suficientes para autorizar este processo."
        ),
        task_manager=SimpleNamespace(should_cancel=lambda *_: False),
        _encerrar_falha=lambda codigo, mensagem, rodada: ("blocked", codigo, rodada),
    )

    resultado = verificar_antes_de_agir(
        harness, "feche a Steam por completo", acoes,
        [{"ferramenta": "listar_processos_windows", "resultado": "steamservice.exe | PID 10760"}],
        rodada=3,
        resposta_wrapper=lambda x: x,
        write_log=lambda nome, **dados: eventos.append((nome, dados)),
    )
    assert resultado == ("blocked", "intent_verification_blocked", 3)
    registro = next(dados for nome, dados in eventos if nome == "INTENT_VERIFICATION_RESULT")
    assert registro["decisao"] == "bloquear"
    assert "evidencias" in registro["motivo"]
    assert registro["propostas"] == [
        {"ferramenta": "encerrar_processo_windows", "nome_processo": "steamservice.exe", "pid": 10760}
    ]


def test_proposta_invalida_nao_injeta_argumentos_no_log():
    resultado = _diagnostico_propostas_bloqueadas([
        _call("encerrar_processo_windows", '{"nome":"steam.exe; taskkill /f","pid":true}'),
        _call("encerrar_processo_windows", "not-json"),
    ])
    assert resultado == [
        {"ferramenta": "encerrar_processo_windows"},
        {"ferramenta": "encerrar_processo_windows"},
    ]
