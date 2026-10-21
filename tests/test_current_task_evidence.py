"""Fresh proof belongs to a task, never to another task's context. No API."""
import json
from types import SimpleNamespace

import pytest

from core.harness import AurenHarness
from core.permission_manager import PermissionManager
from core.session import SessionContextManager
from core.task_manager import TaskManager, TaskState
from core.tool_result import ToolResult


def response(text='', call=None):
    return SimpleNamespace(output=[call] if call else [], output_text=text, usage=None)


def harness(tmp_path, model, executor=None, *, persistent=True):
    manager = TaskManager(db_path=tmp_path/'tasks.sqlite3' if persistent else None)
    pm = PermissionManager()
    h = AurenHarness(task_manager=manager, permission_manager=pm,
        context=SessionContextManager(), criar_resposta=model,
        executar_ferramenta=executor or (lambda c:pytest.fail('Unexpected effect')),
        obter_chamadas=lambda r:r.output, comando_rapido=lambda _:(False,''),
        mostrar_uso=lambda:None, iniciar_tarefa=pm.iniciar_tarefa, apos_tarefa=None,
        fechar=lambda:None, max_model_rounds=2)
    chat = h._garantir_sessao_chat()
    old = manager.create('Leia "ficticio.txt".', chat_id=chat)
    manager.start()
    manager.begin_step('ler_arquivo', '{"caminho":"ficticio.txt","inicio":0,"limite_caracteres":200}')
    manager.finish_step(success=True, result='CODIGO_ANTIGO: 19 itens.')
    manager.complete('CODIGO_ANTIGO: 19 itens.')
    return h, old.task_id


@pytest.mark.parametrize('goal', [
    'Leia "ficticio.txt" com inicio=0 e limite_caracteres=200.',
    'Qual o conteúdo do arquivo "ficticio.txt"?',
    'Leia a página atual do navegador.',
    'Qual o título da aba atual?',
    'Qual o volume atual do Windows?',
    'Liste as janelas abertas.',
    'Qual o status atual do Windows?',
])
@pytest.mark.parametrize('persistent', [False, True])
def test_previous_answer_without_current_tool_is_never_completed(tmp_path, goal, persistent):
    inputs = []
    def model(state, *args):
        inputs.append(str(state))
        return response('CODIGO_ANTIGO: 19 itens.')
    h, old = harness(tmp_path, model, persistent=persistent)
    try:
        h.processar_mensagem(goal)
        current = h.current_task()
        assert current.task_id != old and current.steps == ()
        assert current.state is TaskState.FAILED
        assert h.task_manager.get_snapshot(old).state is TaskState.COMPLETED
        assert any('CODIGO_ANTIGO' in value for value in inputs)
    finally:
        h.shutdown()


@pytest.mark.parametrize('goal', [
    'ola auren', 'Quanto é 2 + 2?', 'Explique como ler um arquivo TXT.',
    'Como posso abrir uma página no navegador?',
    'Explique o que significa volume no Windows.',
    'Leia este texto: "o arquivo ficticio.txt é um exemplo".',
    'Resuma o conteúdo que você acabou de ler, sem acessar o arquivo novamente.',
    'Qual o volume de uma esfera de raio 2?', 'Qual o status HTTP 200?',
])
def test_conversation_and_supplied_data_need_no_tool(tmp_path, goal):
    seen = []
    def model(state, *args):
        seen.append(args)
        return response('Resposta conversacional fictícia.')
    h, _ = harness(tmp_path, model)
    try:
        h.processar_mensagem(goal)
        assert h.current_task().state is TaskState.COMPLETED
        assert not h.current_task().steps
        assert len(seen) == 1 and len(seen[0]) == 2  # No tool_choice=required.
    finally:
        h.shutdown()


@pytest.mark.parametrize('goal,tool,args', [
    ('Leia "ficticio.txt".', 'ler_arquivo', {'caminho':'ficticio.txt','inicio':0,'limite_caracteres':200}),
    ('Leia a página atual do navegador.', 'ler_pagina', {}),
    ('Qual o volume atual do Windows?', 'obter_audio_windows', {}),
])
def test_new_task_has_its_own_successful_observation(tmp_path, goal, tool, args):
    call = SimpleNamespace(type='function_call', name=tool, arguments=json.dumps(args), call_id='fresh')
    answers = iter([response(call=call), response('CODIGO_NOVO: 23 itens.')])
    effects = []
    h, old = harness(tmp_path, lambda *a:next(answers),
        lambda c:effects.append(c.name) or ToolResult.success('CODIGO_NOVO: 23 itens.'))
    try:
        h.processar_mensagem(goal)
        assert h.current_task().state is TaskState.COMPLETED
        assert h.current_task().task_id != old
        assert len(h.current_task().steps) == 1
        assert h.current_task().steps[0].success is True
        assert effects == [tool]
    finally:
        h.shutdown()


def test_an_unrelated_successful_query_is_not_file_read_evidence(tmp_path):
    call = SimpleNamespace(type='function_call', name='obter_audio_windows', arguments='{}', call_id='wrong')
    answers = iter([response(call=call), response('Arquivo lido: CODIGO_ANTIGO.')])
    h, _ = harness(tmp_path, lambda *a:next(answers), lambda c:ToolResult.success('Volume fictício: 20'))
    try:
        h.processar_mensagem('Leia "ficticio.txt".')
        assert h.current_task().state is TaskState.FAILED
    finally:
        h.shutdown()


def test_reading_another_file_does_not_prove_the_requested_target(tmp_path):
    call = SimpleNamespace(type='function_call', name='ler_arquivo', call_id='wrong-file',
        arguments='{"caminho":"outro.txt","inicio":0,"limite_caracteres":200}')
    answers = iter([response(call=call), response('Arquivo lido.')])
    h, _ = harness(tmp_path, lambda *a:next(answers), lambda c:ToolResult.success('Outro arquivo fictício'))
    try:
        h.processar_mensagem('Leia "ficticio.txt".')
        assert h.current_task().state is TaskState.FAILED
    finally:
        h.shutdown()


def test_an_observation_does_not_prove_a_requested_effect(tmp_path):
    call = SimpleNamespace(type='function_call', name='listar_janelas_windows', arguments='{}', call_id='observe')
    answers = iter([response(call=call), response('Janela maximizada.')])
    h, _ = harness(tmp_path, lambda *a:next(answers), lambda c:ToolResult.success('Janela fictícia ALFA'))
    try:
        h.processar_mensagem('Maximize a janela ALFA')
        assert h.current_task().state is TaskState.FAILED
    finally:
        h.shutdown()


def test_listing_tabs_does_not_prove_page_content(tmp_path):
    call = SimpleNamespace(type='function_call', name='listar_abas', arguments='{}', call_id='tabs')
    answers = iter([response(call=call), response('Conteúdo antigo da página.')])
    h, _ = harness(tmp_path, lambda *a:next(answers), lambda c:ToolResult.success('Aba ALFA fictícia'))
    try:
        h.processar_mensagem('Leia a página atual do navegador.')
        assert h.current_task().state is TaskState.FAILED
    finally:
        h.shutdown()


def test_denial_cannot_become_completed_or_reach_the_handler(tmp_path, monkeypatch):
    from core.permission_manager import PermissionLevel
    from tools import dispatcher
    call = SimpleNamespace(type='function_call', name='ler_arquivo', call_id='denied',
        arguments='{"caminho":"ficticio.txt","inicio":0,"limite_caracteres":200}')
    answers = iter([response(call=call), response('Leitura concluída.')])
    h, _ = harness(tmp_path, lambda *a:next(answers))
    h.permission_manager.policy['file.read'] = PermissionLevel.BLOCKED
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, 'ler_arquivo', lambda *a:pytest.fail('Denied effect ran'))
    h.executar_ferramenta = lambda c:dispatcher.executar_ferramenta(c,h.permission_manager,None)
    try:
        h.processar_mensagem('Leia "ficticio.txt".')
        assert h.current_task().state is TaskState.FAILED
        assert len(h.current_task().steps) == 1 and h.current_task().steps[0].success is False
    finally:
        h.shutdown()


def test_own_checkpoint_observation_is_sufficient_without_repeating_it(tmp_path):
    from agent.planner import PlanBuilder
    h, _ = harness(tmp_path, lambda *a:pytest.fail('No new model call needed'))
    try:
        goal = 'Leia "ficticio.txt".'
        task = h.task_manager.create(goal, chat_id=h._session.chat_id, plan=PlanBuilder.build(goal))
        h._task_id = task.task_id
        h.task_manager.start()
        h.task_manager.configure_model_budget(3)
        h.task_manager.begin_step('ler_arquivo','{"caminho":"ficticio.txt","inicio":0,"limite_caracteres":200}')
        h.task_manager.finish_step(success=True,result='Conteúdo comprovado nesta tarefa.')
        h.task_manager.save_execution_checkpoint(h.permission_manager.checkpoint_limits())
        h.task_manager.pause()
        h.task_manager.resume_checkpoint(task.task_id)
        assert h._verify_completion(goal, candidate_answer='Conteúdo comprovado nesta tarefa.') is None
        assert len(h.current_task().steps) == 1
    finally:
        h.shutdown()


@pytest.mark.parametrize('candidate', ['Qual arquivo devo ler?', 'Já li o arquivo. Qual arquivo devo ler?'])
def test_real_clarification_is_displayed_without_claiming_read_completion(tmp_path, candidate):
    h, _ = harness(tmp_path, lambda *a:response(candidate))
    try:
        _, answer = h.processar_mensagem('Leia o arquivo')
        assert h.current_task().state is TaskState.WAITING and not h.current_task().steps
        assert 'Qual arquivo devo ler?' in answer.output_text
        assert 'Já li o arquivo.' not in answer.output_text
        assert h._pergunta_pendente is not None
    finally:
        h.shutdown()
