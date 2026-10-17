"""Regressoes Live A01: nao trocar um executavel absoluto por app fuzzy."""

from core.permission_manager import PermissionLevel, PermissionManager
from tools import applications


EXE = r"C:\AurenLiveTest\run-20261016-230910\AurenLiveEditor.exe"


def _nao_pode_buscar(*args, **kwargs):
    raise AssertionError("caminho explicito nao pode usar busca fuzzy")


def test_executavel_absoluto_tem_prioridade_e_nao_alega_janela_aberta(monkeypatch):
    invocacoes = []

    def popen(args, **kwargs):
        invocacoes.append((args, kwargs))
        return object()

    monkeypatch.setattr(applications, "encontrar_aplicativo", _nao_pode_buscar)
    monkeypatch.setattr(applications, "procurar_atalho", _nao_pode_buscar)
    monkeypatch.setattr(applications, "procurar_executavel", _nao_pode_buscar)
    monkeypatch.setattr(applications.os.path, "isfile", lambda path: path == EXE)
    monkeypatch.setattr(applications.subprocess, "Popen", popen)

    texto = applications.abrir_programa(f'"{EXE}"')

    assert invocacoes[0][0] == [EXE]
    assert len(invocacoes) == 1
    assert "solicitada" in texto
    assert "ainda nao foi verificada" in texto
    assert "foi aberto" not in texto


def test_executavel_absoluto_inexistente_nao_abre_outro_app(monkeypatch):
    monkeypatch.setattr(applications, "encontrar_aplicativo", _nao_pode_buscar)
    monkeypatch.setattr(applications, "procurar_atalho", _nao_pode_buscar)
    monkeypatch.setattr(applications.os.path, "isfile", lambda path: False)
    monkeypatch.setattr(applications.subprocess, "Popen", _nao_pode_buscar)

    texto = applications.abrir_programa(EXE)

    assert "ACAO NAO EXECUTADA" in texto
    assert "nao existe" in texto


def test_caminho_explicito_bat_nao_e_executado(monkeypatch):
    monkeypatch.setattr(applications, "encontrar_aplicativo", _nao_pode_buscar)
    monkeypatch.setattr(applications.os.path, "isfile", _nao_pode_buscar)
    monkeypatch.setattr(applications.subprocess, "Popen", _nao_pode_buscar)

    assert "ACAO NAO EXECUTADA" in applications.abrir_programa(
        r"C:\AurenLiveTest\comandos.bat"
    )


def test_falha_popen_nao_reporta_sucesso(monkeypatch):
    monkeypatch.setattr(applications, "encontrar_aplicativo", _nao_pode_buscar)
    monkeypatch.setattr(applications.os.path, "isfile", lambda path: True)

    def falha(*args, **kwargs):
        raise OSError("acesso negado")

    monkeypatch.setattr(applications.subprocess, "Popen", falha)
    texto = applications.abrir_programa(EXE)

    assert "ACAO NAO EXECUTADA" in texto
    assert "acesso negado" in texto


def test_caminho_absoluto_exige_confirmacao_de_permissao():
    # A classificacao do PermissionManager nao depende de estado de tarefa.
    policy = object.__new__(PermissionManager)
    nivel, motivo = policy._classificar_programa({"programa": EXE})

    assert nivel == PermissionLevel.CONFIRM
    assert "confirmacao" in motivo


def test_atalho_de_nome_normal_preserva_politica_auto():
    policy = object.__new__(PermissionManager)
    nivel, _ = policy._classificar_programa({"programa": "Calculadora"})

    assert nivel == PermissionLevel.AUTO
