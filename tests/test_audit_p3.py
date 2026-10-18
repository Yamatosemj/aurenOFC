import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.orchestrator import AurenOrchestrator
from core.harness_intent_guard import verificar_antes_de_agir
from providers.openai_provider import OpenAIProvider
from tools import file_intelligence, files, windows_uia
from medir_metricas_router import parse_tasks


def test_aud016_csv_detection_reads_only_sample(monkeypatch, tmp_path):
    sizes = []
    class Sample(io.StringIO):
        def read(self, size=-1):
            sizes.append(size)
            assert 0 < size <= 16384
            return super().read(size)
    monkeypatch.setattr(file_intelligence, "_detect_encoding", lambda *a: "utf-8")
    monkeypatch.setattr(file_intelligence, "_open_read", lambda *a, **kw: Sample("a,b\n1,2\n" * 10000))
    assert file_intelligence._detect_type(tmp_path / "fake.csv")[0] == "CSV"
    assert sizes == [16384]


@pytest.mark.parametrize("second", [{"response_id": "B"}, {"reasoning_effort": "high"}])
def test_aud018_cache_does_not_reuse_another_context(second):
    requests = []
    provider = SimpleNamespace(name="ficticio", create_response=lambda *a, **kw:
        requests.append(kw) or SimpleNamespace(output=[], output_text="resposta ficticia"))
    orchestrator = AurenOrchestrator(provider=provider)
    orchestrator.create_response("ola", **({"response_id": "A"} if "response_id" in second else {}))
    orchestrator.create_response("ola", **second)
    assert len(requests) == 2


def test_aud020_review_usage_reaches_task_trace(monkeypatch):
    from core import usage
    monkeypatch.setattr(usage, "registrar_uso", lambda _: None)
    response = SimpleNamespace(output_text='{"decisao":"aprovar","motivo":"ficticio","pergunta":""}',
                               usage=SimpleNamespace(input_tokens=11, output_tokens=3, input_tokens_details=None))
    provider = OpenAIProvider()
    monkeypatch.setattr(provider, "get_client", lambda: SimpleNamespace(responses=SimpleNamespace(create=lambda **kw: response)))
    traces = []
    harness = SimpleNamespace(_task_id="ficticio", _trace=SimpleNamespace(record_model=lambda *a: traces.append(a)),
        verificar_intencao=provider.verify_intent, task_manager=SimpleNamespace(should_cancel=lambda _: False))
    result = verificar_antes_de_agir(harness, "ajuste conforme o pedido detalhado", [SimpleNamespace(
        name="definir_volume_windows", arguments='{"percentual":30}')], [], rodada=1,
        resposta_wrapper=lambda x: x, write_log=lambda *a, **kw: None)
    assert result is None
    assert len(traces) == 1
    assert traces[0][2]["input_tokens"] == 11
    assert traces[0][2]["output_tokens"] == 3


def test_aud021_documents_do_not_present_old_bugs_as_current():
    root = Path(__file__).resolve().parents[1]
    assert "ultima ferramenta pode substituir" not in (root / "docs/architecture/01-nucleo.md").read_text(encoding="utf-8")
    assert "| Override bloqueado na fachada" not in (root / "docs/architecture/03-modelo-sessao-memoria.md").read_text(encoding="utf-8")
    assert "Standby recusa novas mensagens" not in (root / "docs/architecture/07-interface-desktop-gui.md").read_text(encoding="utf-8")


def test_aud029_name_search_does_not_return_unrelated_file(tmp_path, monkeypatch):
    root = tmp_path / "profile"
    folder = root / "Downloads"
    folder.mkdir(parents=True)
    (folder / "qualquer.txt").write_text("ficticio")
    monkeypatch.setenv("USERPROFILE", str(root))
    for key in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        monkeypatch.delenv(key, raising=False)
    result = files.buscar_arquivo("nomeinexistente742")
    assert "qualquer.txt" not in result
    assert "Nao encontrei" in result


@pytest.mark.parametrize("kind", ["timeout", "error"])
def test_aud031_failed_uia_removes_both_temporaries(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(windows_uia.tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(windows_uia.shutil, "which", lambda _: "powershell-ficticio")
    def fail(*a, **kw):
        if kind == "timeout":
            raise windows_uia.subprocess.TimeoutExpired("ficticio", 20)
        raise OSError("ficticio")
    monkeypatch.setattr(windows_uia.subprocess, "run", fail)
    assert windows_uia._executar_ui_automation("inspecionar", {})["ok"] is False
    assert list(tmp_path.iterdir()) == []


def test_aud032_multiline_end_reads_named_status_only():
    prefix = "[2026-10-17T12:00:00-03:00] "
    text = prefix + "TASK_START\n  task_id: ficticio\n"
    text += prefix + "TASK_END\n  task_id: ficticio\n  status: completed\n  outro: nao-e-status\n"
    text += prefix + "CHAT_END\n  status: failed\n"
    assert parse_tasks(text)[0]["status"] == "completed"
