from types import SimpleNamespace

import pytest

from providers.model_ladder import (
    COOLDOWN_GONE_SECONDS,
    COOLDOWN_QUOTA_SECONDS,
    COOLDOWN_UNAVAILABLE_SECONDS,
    ModelLadder,
    ModelLadderExhaustedError,
    ModelLadderHistoryRequiredError,
)


class RelogioFake:
    def __init__(self, value: float = 1000.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


class ErroHttp(RuntimeError):
    def __init__(self, status_code: int, message: str | None = None) -> None:
        super().__init__(message or f"HTTP {status_code}")
        self.status_code = status_code


def test_primeiro_modelo_ok_faz_uma_chamada():
    chamadas: list[str] = []
    ladder = ModelLadder(("modelo-a", "modelo-b"))

    modelo, resposta = ladder.executar(
        lambda model: chamadas.append(model) or {"ok": True}
    )

    assert modelo == "modelo-a"
    assert resposta == {"ok": True}
    assert chamadas == ["modelo-a"]


def test_429_troca_e_esfria_por_5_minutos():
    relogio = RelogioFake()
    chamadas: list[str] = []

    def chamar(model: str):
        chamadas.append(model)
        if model == "modelo-a":
            raise ErroHttp(429)
        return "ok"

    ladder = ModelLadder(("modelo-a", "modelo-b"), clock=relogio)
    modelo, resposta = ladder.executar(chamar)

    assert modelo == "modelo-b"
    assert resposta == "ok"
    assert chamadas == ["modelo-a", "modelo-b"]
    assert ladder.cooldown_restante("modelo-a") == pytest.approx(
        COOLDOWN_QUOTA_SECONDS
    )
    assert ladder.esta_em_cooldown("modelo-a")


def test_503_troca_e_esfria_por_30_minutos():
    relogio = RelogioFake()
    ladder = ModelLadder(("modelo-a", "modelo-b"), clock=relogio)

    def chamar(model: str):
        if model == "modelo-a":
            raise ErroHttp(503)
        return "ok"

    modelo, resposta = ladder.executar(chamar)

    assert modelo == "modelo-b"
    assert resposta == "ok"
    assert ladder.cooldown_restante("modelo-a") == pytest.approx(
        COOLDOWN_UNAVAILABLE_SECONDS
    )


def test_404_troca_e_esfria_por_6_horas():
    relogio = RelogioFake()
    ladder = ModelLadder(("modelo-a", "modelo-b"), clock=relogio)

    def chamar(model: str):
        if model == "modelo-a":
            raise ErroHttp(404)
        return "ok"

    modelo, resposta = ladder.executar(chamar)

    assert modelo == "modelo-b"
    assert resposta == "ok"
    assert ladder.cooldown_restante("modelo-a") == pytest.approx(
        COOLDOWN_GONE_SECONDS
    )


@pytest.mark.parametrize("status_code", [400, 401])
def test_erros_400_e_401_nao_trocam_modelo(status_code: int):
    chamadas: list[str] = []
    ladder = ModelLadder(("modelo-a", "modelo-b"))

    def chamar(model: str):
        chamadas.append(model)
        raise ErroHttp(status_code)

    with pytest.raises(ErroHttp) as exc_info:
        ladder.executar(chamar)

    assert exc_info.value.status_code == status_code
    assert chamadas == ["modelo-a"]
    assert not ladder.esta_em_cooldown("modelo-a")


def test_todos_em_cooldown_produz_erro_estruturado_claro():
    relogio = RelogioFake()
    ladder = ModelLadder(("modelo-a", "modelo-b"), clock=relogio)

    def primeira_chamada(model: str):
        if model == "modelo-a":
            raise ErroHttp(429)
        return "ok"

    def segunda_chamada(_model: str):
        raise ErroHttp(503)

    ladder.executar(primeira_chamada)

    with pytest.raises(ModelLadderExhaustedError) as exc_info:
        ladder.executar(segunda_chamada)

    erro = exc_info.value
    assert erro.code == "model_ladder_exhausted"
    assert erro.data["modelos"] == ["modelo-a", "modelo-b"]
    assert "cooldowns_restantes_s" in erro.data
    assert "modelo-a" in str(erro)
    assert "modelo-b" in str(erro)


def test_cooldown_expira_e_modelo_volta_a_ser_elegivel():
    relogio = RelogioFake()
    ladder = ModelLadder(("modelo-a", "modelo-b"), clock=relogio)

    def primeira_chamada(model: str):
        if model == "modelo-a":
            raise ErroHttp(429)
        return "ok"

    ladder.executar(primeira_chamada)
    relogio.value += COOLDOWN_QUOTA_SECONDS - 1
    assert ladder.esta_em_cooldown("modelo-a")
    relogio.value += 1

    chamadas: list[str] = []
    modelo, resposta = ladder.executar(
        lambda model: chamadas.append(model) or "voltou"
    )

    assert modelo == "modelo-a"
    assert resposta == "voltou"
    assert chamadas == ["modelo-a"]


def test_modelo_em_cooldown_e_pulado_sem_nova_chamada():
    relogio = RelogioFake()
    ladder = ModelLadder(("modelo-a", "modelo-b"), clock=relogio)
    def primeira_chamada(model: str):
        if model == "modelo-a":
            raise ErroHttp(429)
        return "ok"

    ladder.executar(primeira_chamada)

    chamadas: list[str] = []
    modelo, resposta = ladder.executar(
        lambda model: chamadas.append(model) or "segunda"
    )

    assert modelo == "modelo-b"
    assert resposta == "segunda"
    assert chamadas == ["modelo-b"]


def test_timeout_e_classificado_como_indisponivel():
    relogio = RelogioFake()
    ladder = ModelLadder(("modelo-a", "modelo-b"), clock=relogio)

    def chamar(model: str):
        if model == "modelo-a":
            raise TimeoutError("request timed out")
        return "ok"

    modelo, resposta = ladder.executar(chamar)

    assert modelo == "modelo-b"
    assert resposta == "ok"
    assert ladder.cooldown_restante("modelo-a") == pytest.approx(
        COOLDOWN_UNAVAILABLE_SECONDS
    )


def test_log_informa_modelo_esfriado_e_proximo():
    class LoggerFake:
        def __init__(self):
            self.messages = []

        def warning(self, message, *args):
            self.messages.append(message % args)

    logger = LoggerFake()
    ladder = ModelLadder(("modelo-a", "modelo-b"), logger=logger)

    def primeira_chamada(model: str):
        if model == "modelo-a":
            raise ErroHttp(503)
        return "ok"

    ladder.executar(primeira_chamada)

    assert logger.messages == [
        "modelo modelo-a em cooldown por 30 min, usando modelo-b"
    ]


def test_troca_com_previous_response_id_reenvia_historico_completo():
    from providers.openai_provider import OpenAIProvider

    class FakeResponses:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                raise ErroHttp(429)
            return SimpleNamespace(output_text="ok", output=[], usage=None)

    class FakeClient:
        def __init__(self):
            self.responses = FakeResponses()

    relogio = RelogioFake()
    provider = OpenAIProvider()
    provider._client = FakeClient()
    provider._ladder = ModelLadder(
        ("modelo-a", "modelo-b"),
        clock=relogio,
    )

    historico = [
        {"role": "user", "content": [{"type": "input_text", "text": "historico"}]}
    ]
    resposta = provider.create_response(
        "entrada-atual",
        response_id="resp_123",
        historico_completo=historico,
        tools=[],
    )

    assert resposta.output_text == "ok"
    primeira, segunda = provider._client.responses.calls
    assert primeira["model"] == "modelo-a"
    assert primeira["previous_response_id"] == "resp_123"
    assert primeira["input"] == "entrada-atual"
    assert segunda["model"] == "modelo-b"
    assert "previous_response_id" not in segunda
    assert segunda["input"] == historico


def test_troca_com_previous_response_id_sem_historico_falha_explicitamente():
    from providers.openai_provider import OpenAIProvider

    class FakeResponses:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            raise ErroHttp(429)

    class FakeClient:
        def __init__(self):
            self.responses = FakeResponses()

    provider = OpenAIProvider()
    provider._client = FakeClient()
    provider._ladder = ModelLadder(("modelo-a", "modelo-b"))

    with pytest.raises(ModelLadderHistoryRequiredError) as exc_info:
        provider.create_response(
            "entrada-atual",
            response_id="resp_123",
            tools=[],
        )

    assert exc_info.value.code == "model_ladder_history_required"
    assert exc_info.value.data["modelo_destino"] == "modelo-b"
    assert len(provider._client.responses.calls) == 1


def test_provider_configura_timeout_e_desativa_retry_interno(monkeypatch):
    import sys
    import types

    import providers.openai_provider as provider_module

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_openai = SimpleNamespace(OpenAI=FakeOpenAI)
    monkeypatch.setitem(sys.modules, "openai", fake_openai)

    provider = provider_module.OpenAIProvider()
    client = provider.get_client()

    assert client.kwargs["timeout"] == provider_module.AUREN_REQUEST_TIMEOUT_S
    assert client.kwargs["max_retries"] == 0


def test_usage_registra_o_modelo_que_responde():
    from core import usage

    usage.session_model_counts.clear()
    usage.last_response_model = None

    resposta = SimpleNamespace(
        model="modelo-b",
        usage=SimpleNamespace(
            input_tokens=10,
            output_tokens=5,
            input_tokens_details=None,
        ),
    )

    usage.registrar_uso(resposta, modelo="modelo-b")

    assert usage.last_response_model == "modelo-b"
    assert usage.session_model_counts["modelo-b"] == 1
