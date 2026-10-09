"""Testes da camada unica Session/Context (core/session.py)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

from core.harness import AurenHarness
from core.session import SessionContextManager
from core.task_manager import TaskManager
from memory.store import PersistentMemoryStore
from skills.loader import SkillLibrary

ROOT = Path(__file__).resolve().parents[1]


def _store(tmp_path) -> PersistentMemoryStore:
    return PersistentMemoryStore(tmp_path / "memory.sqlite3")


def _harness(tmp_path, monkeypatch, context, *, fast=None, **extra):
    """Harness real com modelo falso; captura o estado enviado ao modelo."""
    import core.harness as harness_mod

    monkeypatch.setattr(harness_mod, "CHAT_LOGS_DIR", tmp_path / "chats")
    monkeypatch.setattr(harness_mod, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(harness_mod, "LOG_FILE", tmp_path / "logs" / "auren.log")
    monkeypatch.setattr(harness_mod, "TASK_LOG_DIR", tmp_path / "logs" / "tarefas")
    enviados: list[str] = []

    def criar_resposta(estado, *_a, **_k):
        enviados.append(str(estado))
        return SimpleNamespace(output=[], output_text=f"resposta {len(enviados)}", usage=None)

    harness = AurenHarness(
        criar_resposta=criar_resposta,
        executar_ferramenta=lambda _item: "ok",
        mostrar_uso=lambda: None,
        obter_chamadas=lambda response: [],
        comando_rapido=fast or (lambda _msg: (False, "")),
        iniciar_tarefa=lambda: None,
        apos_tarefa=None,
        fechar=lambda: None,
        context=context,
        **extra,
    )
    return harness, enviados


# --------------------------------------------------------------- Session/Context
def test_sem_historico_nao_gera_contexto(tmp_path):
    ctx = SessionContextManager(_store(tmp_path))
    snap = ctx.build("chat-novo", "qual a capital da frança")
    assert snap.turnos == ()
    assert snap.vazio and snap.texto == ""
    assert snap.erros == ()


def test_sem_store_e_sem_skills_e_inerte():
    ctx = SessionContextManager()
    assert ctx.persiste is False
    assert ctx.build("c", "qualquer coisa").vazio
    assert ctx.record_turn("c", "user", "oi")["ok"] is False


def test_sem_chat_id_nao_devolve_historico(tmp_path):
    store = _store(tmp_path)
    store.registrar_conversa("chat-A", "user", "algo guardado")
    ctx = SessionContextManager(store)
    assert ctx.build("", "algo guardado").turnos == ()
    assert ctx.build(None, "algo guardado").turnos == ()


def test_historico_curto_em_ordem_cronologica(tmp_path):
    ctx = SessionContextManager(_store(tmp_path))
    ctx.record_turn("chat-A", "user", "pesquise receitas de bolo")
    ctx.record_turn("chat-A", "assistant", "Achei 3 receitas.")
    snap = ctx.build("chat-A", "e agora?")
    assert [(t.papel, t.conteudo) for t in snap.turnos] == [
        ("user", "pesquise receitas de bolo"),
        ("assistant", "Achei 3 receitas."),
    ]
    texto = snap.secao("turnos")
    assert texto.index("receitas de bolo") < texto.index("Achei 3 receitas")


def test_historico_longo_mantem_so_os_ultimos_turnos(tmp_path):
    ctx = SessionContextManager(_store(tmp_path), turnos_recentes=4)
    for i in range(20):
        ctx.record_turn("chat-A", "user" if i % 2 == 0 else "assistant", f"turno-{i:02d}")
    snap = ctx.build("chat-A", "continua")
    assert [t.conteudo for t in snap.turnos] == ["turno-16", "turno-17", "turno-18", "turno-19"]


def test_turnos_sao_truncados_por_papel(tmp_path):
    ctx = SessionContextManager(_store(tmp_path), max_chars_user=50, max_chars_assistant=120)
    ctx.record_turn("c", "user", "u" * 500)
    ctx.record_turn("c", "assistant", "a" * 500)
    texto = ctx.build("c", "x").secao("turnos")
    assert "u" * 51 not in texto and "a" * 121 not in texto
    assert "a" * 100 in texto


def test_sessoes_isoladas(tmp_path):
    store = _store(tmp_path)
    ctx = SessionContextManager(store)
    ctx.record_turn("chat-A", "user", "marcador-do-chat-A unico")
    ctx.record_turn("chat-B", "user", "assunto-do-chat-B unico")
    a = ctx.build("chat-A", "marcador-do-chat-A unico")
    b = ctx.build("chat-B", "marcador-do-chat-A unico")
    assert "marcador-do-chat-A" in a.texto
    assert "marcador-do-chat-A" not in b.texto
    assert "assunto-do-chat-B" in b.texto and "assunto-do-chat-B" not in a.texto


def test_tarefas_anteriores_nao_vazam_entre_chats():
    tm = TaskManager()
    for chat in ("chat-A", "chat-B"):
        t = tm.create(f"pedido do {chat}", chat_id=chat)
        tm.start(t.task_id)
        tm.complete("ok", task_id=t.task_id)
    assert [s.objective for s in tm.recent_snapshots("chat-A")] == ["pedido do chat-A"]
    assert tm.recent_snapshots(None) == () and tm.recent_snapshots("") == ()


def test_continuidade_abre_o_segundo_resultado(tmp_path):
    """"pesquisa X" -> "abre o segundo resultado": nenhum termo em comum, so recencia."""
    store = _store(tmp_path)
    # Ruido antigo: a busca por substring em centenas de linhas nao pode ser a fonte.
    for i in range(350):
        store.registrar_conversa("chat-A", "user", f"conversa antiga {i} sobre assuntos diversos")
    ctx = SessionContextManager(store)
    ctx.record_turn("chat-A", "user", "pesquise melhores teclados mecanicos")
    ctx.record_turn(
        "chat-A", "assistant",
        "Resultados: 1. Teclado Alfa (site-alfa.com) 2. Teclado Beta (site-beta.com) 3. Teclado Gama",
    )

    tm = TaskManager()
    tarefa = tm.create("pesquise melhores teclados mecanicos", chat_id="chat-A")
    tm.start(tarefa.task_id)
    tm.begin_step("navegar_navegador", '{"url":"x"}', task_id=tarefa.task_id)
    tm.finish_step(success=True, result="resultado=2 Teclado Beta https://site-beta.com", task_id=tarefa.task_id)
    tm.complete("ok", task_id=tarefa.task_id)

    snap = ctx.build("chat-A", "abre o segundo resultado", tarefas=tm.recent_snapshots("chat-A"))
    assert "Teclado Beta (site-beta.com)" in snap.secao("turnos")
    assert "https://site-beta.com" in snap.secao("tarefa")
    # So a janela recente entra; o ruido antigo (fora dela) nao depende de busca textual.
    assert "conversa antiga 0 " not in snap.texto and "conversa antiga 100 " not in snap.texto
    assert len(snap.turnos) == 6


def test_tarefa_anterior_nao_repete_clipboard_nem_argumentos():
    tm = TaskManager()
    t = tm.create("leia a area de transferencia", chat_id="c")
    tm.start(t.task_id)
    tm.begin_step("ler_area_transferencia_windows", "{}", task_id=t.task_id)
    tm.finish_step(success=True, result="CONTEUDO PRIVADO DO CLIPBOARD", task_id=t.task_id)
    tm.begin_step("preencher_elemento", '{"texto":"hunter2-valor-digitado"}', task_id=t.task_id)
    tm.finish_step(success=True, result="Campo preenchido", task_id=t.task_id)
    tm.complete("ok", task_id=t.task_id)
    texto = SessionContextManager().build("c", "x", tarefas=tm.recent_snapshots("c")).secao("tarefa")
    assert "PRIVADO" not in texto and "hunter2" not in texto
    assert "Campo preenchido" in texto


def test_memoria_relevante_e_fatos_do_usuario(tmp_path):
    store = _store(tmp_path)
    store.salvar("cor favorita", "azul petroleo", "perfil")
    store.salvar("cafe", "sem acucar", "perfil")
    store.registrar_conversa("chat-A", "user", "meu projeto de energia solar usa inversor hibrido")
    ctx = SessionContextManager(store, turnos_recentes=1)
    ctx.record_turn("chat-A", "user", "outra coisa qualquer mais recente")

    snap = ctx.build("chat-A", "qual era a minha cor favorita e o inversor")
    assert "azul petroleo" in snap.secao("fatos")
    assert "sem acucar" not in snap.secao("fatos")
    assert "inversor hibrido" in snap.secao("memoria")


def test_memoria_nao_duplica_turno_recente(tmp_path):
    ctx = SessionContextManager(_store(tmp_path))
    ctx.record_turn("c", "user", "abrir planilha financeira de setembro")
    snap = ctx.build("c", "planilha financeira")
    assert "planilha financeira" in snap.secao("turnos")
    assert snap.secao("memoria") == ""


def test_objetivo_so_com_palavras_curtas_nao_despeja_ruido(tmp_path):
    store = _store(tmp_path)
    store.salvar("chave qualquer", "valor qualquer")
    store.registrar_conversa("c", "user", "um assunto antigo sem relacao")
    store.salvar_estrategia("tarefa antiga", ["passo"], "ok", True)
    snap = SessionContextManager(store, turnos_recentes=1).build("c", "e o de la?")
    assert snap.secao("fatos") == snap.secao("memoria") == snap.secao("estrategias") == ""


def test_estrategias_gravadas_e_recuperadas_pelo_mesmo_objeto(tmp_path):
    ctx = SessionContextManager(_store(tmp_path))
    assert ctx.record_strategy("abrir site da prefeitura", ["navegar_navegador: ok"], "feito", True, chat_id="c")["ok"]
    snap = ctx.build("c", "abrir o site da prefeitura de novo")
    assert "prefeitura" in snap.secao("estrategias")
    assert "navegar_navegador" in snap.secao("estrategias")


def test_skills_relevantes_entram_e_irrelevantes_nao(tmp_path):
    pasta = tmp_path / "skills" / "planilhas"
    pasta.mkdir(parents=True)
    (pasta / "SKILL.md").write_text(
        "---\nname: planilhas\ndescription: organizar planilhas financeiras\n---\nUse colunas claras.\n",
        encoding="utf-8",
    )
    ctx = SessionContextManager(skills=SkillLibrary(tmp_path / "skills"))
    assert "planilhas" in ctx.build("c", "organize minha planilha financeira").secao("skills")
    assert ctx.build("c", "toque uma musica").secao("skills") == ""


def test_credenciais_nao_sao_persistidas_nem_quebram_o_contexto(tmp_path):
    ctx = SessionContextManager(_store(tmp_path))
    assert ctx.record_turn("c", "user", "minha senha e 1234")["ok"] is False
    assert ctx.build("c", "minha senha").turnos == ()


def test_falha_de_uma_secao_nao_derruba_as_outras(tmp_path):
    store = _store(tmp_path)
    ctx = SessionContextManager(store)
    ctx.record_turn("c", "user", "pergunta antiga sobre baterias")
    store.consultar = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("banco indisponivel"))
    snap = ctx.build("c", "baterias")
    assert "pergunta antiga" in snap.secao("turnos")
    assert any(e.startswith("fatos:") for e in snap.erros)


def test_orcamento_corta_secoes_de_menor_prioridade(tmp_path):
    ctx = SessionContextManager(_store(tmp_path), max_chars=400)
    ctx.record_turn("c", "user", "turno importante para continuidade")
    ctx.record_strategy("estrategia sobre continuidade", ["p" * 300], "r", True, chat_id="c")
    snap = ctx.build("c", "continuidade")
    assert len(snap.texto) <= 400 + 2 * len(snap.secoes)
    assert "turno importante" in snap.texto


# ------------------------------------------------------------------ Harness
def test_harness_envia_historico_do_mesmo_chat_ao_modelo(tmp_path, monkeypatch):
    store = _store(tmp_path)
    harness, enviados = _harness(tmp_path, monkeypatch, SessionContextManager(store))
    harness.processar_mensagem("pesquise teclados mecanicos")
    harness.processar_mensagem("abre o segundo resultado")
    assert "Conversa recente" not in enviados[0]
    assert "pesquise teclados mecanicos" in enviados[1]
    assert "resposta 1" in enviados[1]


def test_harness_grava_turnos_e_respostas_rapidas(tmp_path, monkeypatch):
    store = _store(tmp_path)
    ctx = SessionContextManager(store)
    harness, enviados = _harness(
        tmp_path, monkeypatch, ctx,
        fast=lambda msg: (True, "Volume em 30%") if "volume" in msg else (False, ""),
    )
    harness.processar_mensagem("coloque o volume em 30")
    harness.processar_mensagem("e agora, o que foi feito?")
    assert "Volume em 30%" in enviados[0]  # o modelo recebe o turno do fast path
    chat_id = harness._session.chat_id
    papeis = [(t["papel"], t["conteudo"]) for t in store.ultimas_conversas(chat_id, 10)["resultados"]]
    assert papeis[:2] == [("user", "coloque o volume em 30"), ("assistant", "Volume em 30%")]


def test_harness_sem_context_preserva_comportamento_antigo(tmp_path, monkeypatch):
    harness, enviados = _harness(tmp_path, monkeypatch, None)
    assert harness.context.persiste is False
    harness.processar_mensagem("qual a capital da frança")
    harness.processar_mensagem("e da italia")
    assert "Conversa recente" not in enviados[1]


def test_harness_callbacks_legados_continuam_funcionando(tmp_path, monkeypatch):
    chamadas = []
    harness, enviados = _harness(
        tmp_path, monkeypatch, None,
        registrar_conversa=lambda chat, papel, texto: chamadas.append((papel, texto)),
    )
    harness.processar_mensagem("qual a capital da frança")
    assert chamadas == [("user", "qual a capital da frança"), ("assistant", "resposta 1")]


def test_dois_harnesses_com_o_mesmo_store_nao_misturam_chats(tmp_path, monkeypatch):
    store = _store(tmp_path)
    h1, _ = _harness(tmp_path, monkeypatch, SessionContextManager(store))
    h2, enviados2 = _harness(tmp_path, monkeypatch, SessionContextManager(store))
    h1.processar_mensagem("assunto exclusivo do primeiro chat zebra")
    h2.processar_mensagem("outra pergunta")
    assert "zebra" not in enviados2[0]


# -------------------------------------------------------- texto e voz = mesmo contexto
def test_texto_e_voz_usam_o_mesmo_contexto_no_mesmo_chat(tmp_path, monkeypatch):
    """Na voz, Ctrl direito + Shift direito e texto digitado entram no MESMO harness; a 2a mensagem ve a 1a."""
    store = _store(tmp_path)
    harness, enviados = _harness(tmp_path, monkeypatch, SessionContextManager(store))
    harness.processar_mensagem("pesquise teclados mecanicos")  # chegou por texto
    harness.processar_mensagem("abre o segundo resultado")  # chegou por voz (ASR)
    assert "pesquise teclados mecanicos" in enviados[1]


def _carregar_voice_main(monkeypatch, fake_auren):
    monkeypatch.setitem(sys.modules, "auren", fake_auren)
    spec = importlib.util.spec_from_file_location("_voice_main_sob_teste", ROOT / "voice" / "main.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_voz_monta_o_harness_pela_mesma_fabrica_do_texto(monkeypatch):
    sentinela = object()
    fake_auren = SimpleNamespace(criar_harness=lambda: sentinela)
    voice_main = _carregar_voice_main(monkeypatch, fake_auren)
    assert voice_main._novo_harness() is sentinela


def test_fabrica_unica_injeta_o_mesmo_session_context():
    fonte = (ROOT / "auren.py").read_text(encoding="utf-8")
    assert "def criar_harness" in fonte and "context=session_context" in fonte
    assert fonte.count("AurenHarness(") == 1  # unico ponto de montagem
    voz = (ROOT / "voice" / "main.py").read_text(encoding="utf-8")
    assert "AurenHarness(" not in voz.replace("-> AurenHarness", "")
