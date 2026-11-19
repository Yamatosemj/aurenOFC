"""Offline reproduction of the 2026-11-15 Create Aeronautics conversation."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import core.harness as harness_module
import core.harness_runtime as runtime
from core.harness import AurenHarness
from core.intent_verification import IntentDecision
from core.permission_manager import PermissionManager
from core.task_manager import TaskManager, TaskState
from core.task_trace import TaskTraceStore
from core.tool_result import ToolResult
from tools import dispatcher


GOAL = 'perfeito auren, agora pesquise "create aeronautics" e entre no site com maior relevancia'
GOOGLE_SEARCH = 'https://www.google.com/search?q=create+aeronautics'
RESULT_URL = 'https://example.org/create-aeronautics'


def call(name, **arguments):
    return SimpleNamespace(type='function_call', name=name,
                           arguments=json.dumps(arguments), call_id=name + str(arguments))


def response(*calls, text=''):
    return SimpleNamespace(output=list(calls), output_text=text, usage=None)


@pytest.fixture
def build(tmp_path, monkeypatch):
    # The production logger and trace store must never reach the user's logs.
    monkeypatch.setattr(runtime, 'LOG_DIR', tmp_path / 'logs')
    monkeypatch.setattr(runtime, 'CHAT_LOGS_DIR', tmp_path / 'logs' / 'chats')
    monkeypatch.setattr(runtime, 'TASK_LOG_DIR', tmp_path / 'logs' / 'tarefas')
    monkeypatch.setattr(runtime, 'LOG_FILE', tmp_path / 'logs' / 'auren.log')
    events = []
    monkeypatch.setattr(harness_module, '_write_log',
                        lambda event, **fields: events.append((event, fields)))
    opened = []

    def make(answers, decisions, tool_result=None, *, max_actions=10,
             use_dispatcher=False, confirmation_approved=True, max_model_rounds=None):
        answers, decisions = iter(answers), iter(decisions)
        tools, effects, model_inputs, reviews, confirmations = [], [], [], [], []
        permission = PermissionManager(max_actions=max_actions,
            confirmation_channel=SimpleNamespace(confirmar=lambda request:
                confirmations.append(request) or confirmation_approved))

        def model(text, *_args):
            model_inputs.append(str(text))
            answer = next(answers)
            return answer(text) if callable(answer) else answer

        def review(goal, proposed, history):
            reviews.append((goal, [item.name for item in proposed], list(history)))
            return next(decisions)

        def execute(item):
            tools.append((item.name, json.loads(item.arguments)))
            if use_dispatcher:
                return dispatcher.executar_ferramenta(item, permission, None)
            if tool_result is not None:
                return tool_result(item)
            return ToolResult.success(item.name + ' simulated', tool_name=item.name)

        if use_dispatcher:
            for name in {'preencher_elemento', 'obter_contexto_navegador'}:
                monkeypatch.setitem(dispatcher.TOOL_HANDLERS, name,
                    lambda args, memory, context, tool=name:
                    effects.append((tool, dict(args))) or
                    ToolResult.success(tool + ' simulated', tool_name=tool))

        harness = AurenHarness(
            criar_resposta=model, executar_ferramenta=execute,
            mostrar_uso=lambda: None, obter_chamadas=lambda answer: answer.output,
            comando_rapido=lambda _text: (False, ''),
            iniciar_tarefa=permission.iniciar_tarefa, apos_tarefa=None,
            fechar=lambda: None, verificar_intencao=review,
            permission_manager=permission,
            task_manager=TaskManager(),
            trace_store=TaskTraceStore(tmp_path / ('trace-' + str(len(opened)) + '.sqlite3')),
            **({'max_model_rounds': max_model_rounds} if max_model_rounds is not None else {}),
        )
        opened.append(harness)
        return SimpleNamespace(harness=harness, tools=tools, effects=effects,
                               model_inputs=model_inputs,
                               reviews=reviews, permission=permission,
                               confirmations=confirmations, events=events)

    yield make
    for harness in opened:
        harness._background_queue.shutdown(cancel_pending=True)
        harness._encerrar_sessao_chat('test_closed')


def google_result(item):
    if item.name == 'navegar_navegador' and json.loads(item.arguments).get('url') == GOOGLE_SEARCH:
        return ToolResult.success('URL atual: https://www.google.com/sorry/index',
                                  tool_name=item.name)
    if item.name == 'obter_contexto_navegador':
        return ToolResult.success('Google: trafego incomum; verificacao contra bots',
            data={'abas': 'Aba ativa: 1\nAba 1: Google | https://www.google.com/sorry/index [ATIVA]',
                  'pagina': 'trafego incomum'}, tool_name=item.name)
    if item.name == 'ler_pagina':
        return ToolResult.success(
            'Resultados: Create Aeronautics - Minecraft Mods | ' + RESULT_URL,
            tool_name=item.name)
    return ToolResult.success('opened ' + RESULT_URL, tool_name=item.name)


def google_script():
    return [response(call('navegar_navegador', url=GOOGLE_SEARCH)),
            response(call('obter_contexto_navegador', foco='resultado ou bloqueio')),
            response(call('clicar_elemento', alvo='Create Aeronautics - Minecraft Mods'))]


def test_google_block_waits_without_reviewer_prompt_or_challenge_click(build):
    case = build(google_script(), [IntentDecision('aprovar', 'buscar'),
                                   IntentDecision('aprovar', 'contexto')], google_result)
    _, reply = case.harness.processar_mensagem(GOAL)
    assert case.harness.current_task().state is TaskState.WAITING
    assert 'verificacao' in reply.output_text.lower()
    assert [name for name, _ in case.tools] == [
        'navegar_navegador', 'obter_contexto_navegador']
    assert not case.harness._browser_destination_state.get('verified')


def test_google_block_still_waits_for_simple_search(build):
    case = build([response(call('navegar_navegador', url=GOOGLE_SEARCH)),
                  response(call('obter_contexto_navegador', foco='busca')),
                  response(text='Pesquisa concluida.')],
                 [IntentDecision('aprovar', 'buscar'), IntentDecision('aprovar', 'ler')],
                 google_result)
    case.harness.processar_mensagem('Pesquise Create Aeronautics.')
    assert case.harness.current_task().state is TaskState.WAITING


def test_known_block_url_requires_context_before_any_challenge_click(build):
    case = build([response(call('navegar_navegador', url=GOOGLE_SEARCH)),
                  response(call('clicar_elemento', alvo='Nao sou um robo')),
                  response(text='Concluido.')],
                 [IntentDecision('aprovar', 'buscar'), IntentDecision('aprovar', 'clicar')],
                 google_result)
    case.harness.processar_mensagem(GOAL)
    assert [name for name, _ in case.tools] == ['navegar_navegador']
    assert case.harness.current_task().state is TaskState.FAILED
    assert case.harness.current_task().error == 'browser_block_observation_required'


def test_known_block_url_stops_click_in_same_model_batch(build):
    case = build([response(call('navegar_navegador', url=GOOGLE_SEARCH),
                           call('clicar_elemento', alvo='Nao sou um robo'))],
                 [IntentDecision('aprovar', 'buscar')], google_result)
    case.harness.processar_mensagem(GOAL)
    assert [name for name, _ in case.tools] == ['navegar_navegador']
    assert case.harness.current_task().error == 'browser_block_observation_required'


def test_empty_context_cannot_release_known_google_block_for_click(build):
    def empty_read(item):
        if item.name == 'navegar_navegador':
            return ToolResult.success('URL atual: https://www.google.com/sorry/index',
                                      tool_name=item.name)
        if item.name == 'obter_contexto_navegador':
            return ToolResult.success('Sem dados estruturados', tool_name=item.name)
        return ToolResult.success('Cliquei', tool_name=item.name)

    case = build([response(call('navegar_navegador', url=GOOGLE_SEARCH),
                           call('obter_contexto_navegador', foco='busca'),
                           call('clicar_elemento', alvo='Nao sou um robo'))],
                 [IntentDecision('aprovar', 'buscar')], empty_read)
    case.harness.processar_mensagem('Pesquise Create Aeronautics.')
    assert [name for name, _ in case.tools] == [
        'navegar_navegador', 'obter_contexto_navegador']
    assert case.harness.current_task().state is TaskState.FAILED
    assert case.harness.current_task().error == 'browser_block_observation_required'


def test_suspected_challenge_does_not_claim_success_or_click(build):
    def suspicious(item):
        if item.name == 'obter_contexto_navegador':
            return ToolResult.success('Contexto', data={
                'abas': 'Aba ativa: 1\nAba 1: CAPTCHA | https://site.test/challenge [ATIVA]',
                'pagina': 'Loading',
            }, tool_name=item.name)
        return ToolResult.success('Naveguei', tool_name=item.name)

    case = build([response(call('navegar_navegador', url=GOOGLE_SEARCH)),
                  response(call('obter_contexto_navegador', foco='busca')),
                  response(call('clicar_elemento', alvo='Continuar'))],
                 [IntentDecision('aprovar', 'buscar'), IntentDecision('aprovar', 'clicar')],
                 suspicious)
    case.harness.processar_mensagem(GOAL)
    assert case.harness.current_task().error == 'browser_block_uncertain'
    assert [name for name, _ in case.tools] == [
        'navegar_navegador', 'obter_contexto_navegador']


def test_manual_resolution_rechecks_before_opening_same_task(build):
    state = {'blocked': True, 'url': GOOGLE_SEARCH}

    def tool(item):
        if item.name == 'navegar_navegador':
            state['url'] = json.loads(item.arguments)['url']
            return ToolResult.success('Naveguei', tool_name=item.name)
        if item.name == 'obter_contexto_navegador':
            if state['blocked']:
                return google_result(item)
            if state['url'] == GOOGLE_SEARCH:
                return ToolResult.success('Resultados', data={
                    'abas': f'Aba ativa: 1\nAba 1: Busca | {GOOGLE_SEARCH} [ATIVA]',
                    'pagina': 'Links relevantes:\n- texto=Create Aeronautics - Minecraft Mods | href=' + RESULT_URL,
                }, tool_name=item.name)
            return ToolResult.success('Destino', data={
                'abas': f'Aba ativa: 1\nAba 1: Create Aeronautics - Minecraft Mods | {RESULT_URL} [ATIVA]',
                'pagina': 'Pagina de destino',
            }, tool_name=item.name)
        raise AssertionError(item.name)

    case = build([response(call('navegar_navegador', url=GOOGLE_SEARCH)),
                  response(call('obter_contexto_navegador', foco='busca')),
                  response(call('obter_contexto_navegador', foco='apos verificacao')),
                  response(call('navegar_navegador', url=RESULT_URL)),
                  response(call('obter_contexto_navegador', foco='destino')),
                  response(text='Site aberto.')],
                 [IntentDecision('aprovar', 'passo')] * 5, tool)
    case.harness.processar_mensagem(GOAL)
    waiting = case.harness.current_task()
    assert waiting.state is TaskState.WAITING
    state['blocked'] = False
    case.harness.processar_mensagem('pronto, resolvi a verificacao')
    final = case.harness.current_task()
    assert final.task_id == waiting.task_id
    assert final.state is TaskState.COMPLETED, final.error
    assert [name for name, _ in case.tools].count('navegar_navegador') == 2
    assert [name for name, _ in case.tools][2] == 'obter_contexto_navegador'
    assert case.harness._browser_destination_state.get('verified') is True


def test_persistent_google_block_stops_after_recheck(build):
    case = build([response(call('navegar_navegador', url=GOOGLE_SEARCH)),
                  response(call('obter_contexto_navegador', foco='busca')),
                  response(call('obter_contexto_navegador', foco='apos verificacao')),
                  response(call('clicar_elemento', alvo='Verificar'))],
                 [IntentDecision('aprovar', 'passo')] * 4, google_result)
    case.harness.processar_mensagem(GOAL)
    waiting = case.harness.current_task()
    assert waiting.state is TaskState.WAITING
    case.harness.processar_mensagem('pronto')
    assert case.harness.current_task().task_id == waiting.task_id
    assert case.harness.current_task().state is TaskState.FAILED
    assert case.harness.current_task().error == 'browser_external_blocked'
    assert [name for name, _ in case.tools] == [
        'navegar_navegador', 'obter_contexto_navegador', 'obter_contexto_navegador']


def test_block_resume_rejects_action_before_new_context(build):
    case = build(google_script()[:2] + [
        response(call('clicar_elemento', alvo='Nao sou um robo'))],
        [IntentDecision('aprovar', 'buscar'), IntentDecision('aprovar', 'clicar')],
        google_result)
    case.harness.processar_mensagem(GOAL)
    task_id = case.harness.current_task().task_id
    case.harness.processar_mensagem('pronto')
    assert case.harness.current_task().task_id == task_id
    assert case.harness.current_task().error == 'browser_recheck_required'
    assert [name for name, _ in case.tools] == [
        'navegar_navegador', 'obter_contexto_navegador']


def test_recheck_without_real_browser_state_does_not_release_block(build):
    def missing_after_first(item):
        if item.name == 'obter_contexto_navegador' and reads[0]:
            return ToolResult.success('Sem dados estruturados', tool_name=item.name)
        if item.name == 'obter_contexto_navegador':
            reads[0] += 1
        return google_result(item)

    reads = [0]
    case = build(google_script()[:2] + [
        response(call('obter_contexto_navegador', foco='apos verificacao')),
        response(call('navegar_navegador', url=RESULT_URL))],
        [IntentDecision('aprovar', 'buscar')], missing_after_first)
    case.harness.processar_mensagem(GOAL)
    waiting = case.harness.current_task()
    assert waiting.state is TaskState.WAITING
    case.harness.processar_mensagem('pronto')
    assert case.harness.current_task().task_id == waiting.task_id
    assert case.harness.current_task().error == 'browser_block_uncertain'
    assert [name for name, _ in case.tools] == [
        'navegar_navegador', 'obter_contexto_navegador', 'obter_contexto_navegador']


def test_block_wait_does_not_renew_model_round_limit(build):
    case = build(google_script()[:2],
        [IntentDecision('aprovar', 'buscar')], google_result,
        max_model_rounds=2)
    case.harness.processar_mensagem(GOAL)
    waiting = case.harness.current_task()
    assert waiting.state is TaskState.WAITING
    calls_before = len(case.model_inputs)
    case.harness.processar_mensagem('pronto')
    assert case.harness.current_task().task_id == waiting.task_id
    assert case.harness.current_task().error == 'model_round_limit'
    assert len(case.model_inputs) == calls_before


def test_block_wait_keeps_permission_action_budget(build, monkeypatch):
    state = {'blocked': True}
    case = build([response(call('navegar_navegador', url=GOOGLE_SEARCH, modo='visivel')),
                  response(call('obter_contexto_navegador', foco='busca')),
                  response(call('obter_contexto_navegador', foco='apos verificacao')),
                  response(call('navegar_navegador', url=RESULT_URL, modo='visivel')),
                  response(text='Nao abri.')],
                 [IntentDecision('aprovar', 'buscar'), IntentDecision('aprovar', 'abrir')],
                 max_actions=1, use_dispatcher=True)

    def navigate(args, _memory, _context):
        case.effects.append(('navegar_navegador', dict(args)))
        return ToolResult.success('Naveguei', tool_name='navegar_navegador')

    def context(args, _memory, _context):
        case.effects.append(('obter_contexto_navegador', dict(args)))
        if state['blocked']:
            return ToolResult.success('Bloqueio', data={
                'abas': 'Aba ativa: 1\nAba 1: Google | https://www.google.com/sorry/index [ATIVA]',
                'pagina': 'Trafego incomum',
            }, tool_name='obter_contexto_navegador')
        return ToolResult.success('Resultados', data={
            'abas': f'Aba ativa: 1\nAba 1: Busca | {GOOGLE_SEARCH} [ATIVA]',
            'pagina': 'Links relevantes:\n- texto=Create Aeronautics - Minecraft Mods | href=' + RESULT_URL,
        }, tool_name='obter_contexto_navegador')

    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, 'navegar_navegador', navigate)
    monkeypatch.setitem(dispatcher.TOOL_HANDLERS, 'obter_contexto_navegador', context)
    case.harness.processar_mensagem(GOAL)
    waiting = case.harness.current_task()
    assert waiting.state is TaskState.WAITING
    assert case.permission.actions_attempted == 1
    assert case.permission.last_authorized_action_signature is not None
    state['blocked'] = False
    case.harness.processar_mensagem('pronto')
    assert case.harness.current_task().task_id == waiting.task_id
    assert case.permission.actions_attempted == 1
    assert case.harness.current_task().state is TaskState.FAILED
    assert case.permission.last_authorized_action_tool == 'obter_contexto_navegador'
    assert [name for name, _ in case.effects].count('navegar_navegador') == 1


def test_google_block_keeps_original_task_waiting(build):
    case = build(google_script(),
        [IntentDecision('aprovar', 'buscar'),
         IntentDecision('esclarecer', 'Google bloqueou a busca',
                        'A pesquisa foi bloqueada; devo verificar novamente?')],
        google_result)
    _, answer = case.harness.processar_mensagem(GOAL)
    task = case.harness.current_task()
    assert answer.output_text.endswith('?')
    assert task.state is TaskState.WAITING
    assert task.objective == GOAL and task.finished_at == ''
    assert case.harness.trace_store.get_task(task.task_id)['finished_at'] is None
    assert [step.tool for step in task.steps] == [
        'navegar_navegador', 'obter_contexto_navegador']
    assert [name for name, _ in case.tools] == [
        'navegar_navegador', 'obter_contexto_navegador']
    assert not any(name == 'clicar_elemento' for name, _ in case.tools)
    assert any(name == 'TASK_BROWSER_EXTERNAL_BLOCK' for name, _ in case.events)
    assert any(name == 'TASK_WAITING' and data['task_id'] == task.task_id
               for name, data in case.events)


def test_answer_rechecks_same_id_and_preserves_google_evidence(build):
    case = build(google_script()[:2] + [
        response(call('obter_contexto_navegador', foco='apos verificacao'))],
        [IntentDecision('aprovar', 'buscar'),
         IntentDecision('esclarecer', 'bloqueio externo', 'Devo verificar novamente?')],
        google_result)
    case.harness.processar_mensagem(GOAL)
    original = case.harness.current_task()
    assert original.state is TaskState.WAITING
    case.harness.processar_mensagem('nao, verifique o com maior relevancia')
    final = case.harness.current_task()
    assert final.task_id == original.task_id and final.objective == GOAL
    assert case.harness.trace_store.get_task(final.task_id)['finished_at'] is not None
    assert [step.tool for step in final.steps][:2] == [
        'navegar_navegador', 'obter_contexto_navegador']
    assert [name for name, _ in case.tools].count('navegar_navegador') == 1
    assert [name for name, _ in case.tools].count('obter_contexto_navegador') == 2
    assert final.error == 'browser_external_blocked'


def test_new_request_cancels_waiting_task(build):
    case = build(google_script() + [response(text='Novo pedido atendido.')],
        [IntentDecision('aprovar', 'buscar'),
         IntentDecision('esclarecer', 'bloqueio externo', 'Devo verificar novamente?')],
        google_result)
    case.harness.processar_mensagem(GOAL)
    pending = case.harness.current_task()
    assert pending.state is TaskState.WAITING
    case.harness.processar_mensagem('Consulte o status do Windows.')
    assert case.harness.task_manager.get_snapshot(pending.task_id).state is TaskState.CANCELLED
    assert case.harness.trace_store.get_task(pending.task_id)['status'] == 'cancelled'
    assert case.harness.current_task().task_id != pending.task_id
    assert case.harness.current_task().objective == 'Consulte o status do Windows.'


@pytest.mark.parametrize('new_request', ['agora abre o Spotify', 'quero abrir o Spotify'])
def test_agora_abre_spotify_replaces_waiting_task(build, new_request):
    case = build(google_script() + [response(text='Novo pedido recebido.')],
        [IntentDecision('aprovar', 'buscar'),
         IntentDecision('esclarecer', 'bloqueio externo', 'Devo verificar novamente?')],
        google_result)
    case.harness.processar_mensagem(GOAL)
    old = case.harness.current_task()
    case.harness.processar_mensagem(new_request)
    assert case.harness.task_manager.get_snapshot(old.task_id).state is TaskState.CANCELLED
    assert case.harness.current_task().task_id != old.task_id
    assert case.harness.current_task().objective == new_request


@pytest.mark.parametrize('question,answer', [
    ('Qual resultado devo abrir?', 'quero o segundo'),
    ('Qual resultado devo abrir?', 'abre o primeiro'),
    ('Qual navegador você quer usar?', 'quero o Chrome'),
    ('Com qual aplicativo devo abrir?', 'quero o Chrome'),
])
def test_command_shaped_answer_keeps_original_task(build, question, answer):
    case = build([
        response(call('preencher_elemento', alvo='pendente', texto='valor')),
        response(call('preencher_elemento', alvo='esclarecido', texto='valor')),
        response(text='Entendido.')],
        [IntentDecision('esclarecer', 'alvo incerto', question),
         IntentDecision('aprovar', 'alvo esclarecido')])
    case.harness.processar_mensagem('Abra o resultado escolhido pelo usuario.')
    waiting = case.harness.current_task()
    assert waiting.state is TaskState.WAITING
    case.harness.processar_mensagem(answer)
    assert case.harness.current_task().task_id == waiting.task_id
    assert case.harness.current_task().objective == waiting.objective
    assert any('Esclarecimento do usuario: ' + answer in goal
               for goal, _, _ in case.reviews)


def test_independent_question_replaces_waiting_task(build):
    case = build(google_script() + [response(text='12:00')],
        [IntentDecision('aprovar', 'buscar'),
         IntentDecision('esclarecer', 'bloqueio externo', 'Devo verificar novamente?')],
        google_result)
    case.harness.processar_mensagem(GOAL)
    old = case.harness.current_task()
    assert old.state is TaskState.WAITING
    case.harness.processar_mensagem('que horas são?')
    assert case.harness.task_manager.get_snapshot(old.task_id).state is TaskState.CANCELLED
    assert case.harness.current_task().task_id != old.task_id
    assert case.harness.current_task().objective == 'que horas são?'


def test_lost_pending_question_does_not_leave_orphan_waiting_task(build):
    case = build(google_script() + [response(text='Novo pedido recebido.')],
        [IntentDecision('aprovar', 'buscar'),
         IntentDecision('esclarecer', 'bloqueio externo', 'Devo verificar novamente?')],
        google_result)
    case.harness.processar_mensagem(GOAL)
    old = case.harness.current_task()
    assert old.state is TaskState.WAITING
    case.harness._pergunta_pendente = None
    case.harness.processar_mensagem('Consulte o status do Windows.')
    assert case.harness.task_manager.get_snapshot(old.task_id).state is TaskState.CANCELLED
    assert case.harness.trace_store.get_task(old.task_id)['status'] == 'cancelled'
    assert case.harness.current_task().task_id != old.task_id


def test_cancel_during_wait_is_terminal(build):
    case = build(google_script(),
        [IntentDecision('aprovar', 'buscar'),
         IntentDecision('esclarecer', 'bloqueio externo', 'Devo verificar novamente?')],
        google_result)
    case.harness.processar_mensagem(GOAL)
    pending = case.harness.current_task()
    assert pending.state is TaskState.WAITING
    calls_before = len(case.model_inputs)
    case.harness.processar_mensagem('cancela')
    assert case.harness.current_task().task_id == pending.task_id
    assert case.harness.current_task().state is TaskState.CANCELLED
    assert len(case.model_inputs) == calls_before


def test_nao_esquece_isso_cancels_without_model_or_tool(build):
    case = build(google_script(),
        [IntentDecision('aprovar', 'buscar'),
         IntentDecision('esclarecer', 'bloqueio externo', 'Devo verificar novamente?')],
        google_result)
    case.harness.processar_mensagem(GOAL)
    old = case.harness.current_task()
    model_count, tool_count = len(case.model_inputs), len(case.tools)
    case.harness.processar_mensagem('não, esquece isso')
    assert case.harness.current_task().task_id == old.task_id
    assert case.harness.current_task().state is TaskState.CANCELLED
    assert len(case.model_inputs) == model_count
    assert len(case.tools) == tool_count


@pytest.mark.parametrize('answer', ['sim', 'pode ser'])
def test_short_yes_does_not_claim_manual_verification_was_resolved(build, answer):
    case = build(google_script()[:2] + [
        response(call('obter_contexto_navegador', foco='apos verificacao'))],
        [IntentDecision('aprovar', 'buscar'),
         IntentDecision('esclarecer', 'bloqueio externo', 'Devo verificar novamente?')],
        google_result)
    case.harness.processar_mensagem(GOAL)
    old = case.harness.current_task()
    case.harness.processar_mensagem(answer)
    assert case.harness.current_task().task_id == old.task_id
    assert [name for name, _ in case.tools] == [
        'navegar_navegador', 'obter_contexto_navegador']
    assert case.harness.current_task().state is TaskState.WAITING


def test_completed_effect_is_not_replayed_after_clarification(build):
    case = build([
        response(call('preencher_elemento', alvo='campo 1', texto='primeiro')),
        response(call('preencher_elemento', alvo='campo 2', texto='segundo')),
        response(call('preencher_elemento', texto='primeiro', alvo='campo 1'))],
        [IntentDecision('aprovar', 'primeiro campo'),
         IntentDecision('esclarecer', 'segundo campo incerto', 'Qual outro campo?')])
    case.harness.processar_mensagem('Complete os dois campos conforme minha preferencia.')
    pending = case.harness.current_task()
    assert pending.state is TaskState.WAITING
    assert [step.tool for step in pending.steps] == ['preencher_elemento']
    case.harness.processar_mensagem('campo 2')
    final = case.harness.current_task()
    assert final.task_id == pending.task_id
    assert final.state is TaskState.FAILED
    assert final.error == 'clarification_effect_repeated'
    assert [name for name, _ in case.tools] == ['preencher_elemento']


@pytest.mark.parametrize('answer', ['sim', 'pode ser'])
def test_short_yes_cannot_replay_completed_effect(build, answer):
    case = build([
        response(call('preencher_elemento', alvo='campo 1', texto='primeiro')),
        response(call('preencher_elemento', alvo='campo 2', texto='segundo')),
        response(call('preencher_elemento', texto='primeiro', alvo='campo 1'))],
        [IntentDecision('aprovar', 'primeiro campo'),
         IntentDecision('esclarecer', 'precisa continuar', 'Devo continuar?')])
    case.harness.processar_mensagem('Complete os dois campos conforme minha preferencia.')
    waiting = case.harness.current_task()
    assert waiting.state is TaskState.WAITING
    case.harness.processar_mensagem(answer)
    assert case.harness.current_task().task_id == waiting.task_id
    assert case.harness.current_task().state is TaskState.FAILED
    assert case.harness.current_task().error == 'clarification_effect_repeated'
    assert [name for name, _ in case.tools] == ['preencher_elemento']


def test_reviewer_logs_safe_question_shape_and_proposed_tools(build):
    sensitive_value = 'synthetic-sensitive-value'
    case = build([response(call('preencher_elemento', alvo='campo', texto=sensitive_value))],
        [IntentDecision('esclarecer', 'destino incerto',
                        'Qual conta ' + sensitive_value + ' devo usar?')])
    case.harness.processar_mensagem('Preencha o campo solicitado.')
    request = next(data for name, data in case.events
                   if name == 'INTENT_VERIFICATION_REQUEST')
    decision = next(data for name, data in case.events
                    if name == 'INTENT_VERIFICATION_RESULT')
    assert request['propostas'] == ['preencher_elemento']
    assert decision['pergunta_tipo'] == 'qual'
    assert decision['pergunta_registrada'] is True
    assert sensitive_value not in repr(request) + repr(decision)


def test_permission_budget_survives_clarification(build):
    case = build([
        response(call('preencher_elemento', alvo='campo 1', texto='um', indice=1)),
        response(call('preencher_elemento', alvo='campo 2', texto='dois', indice=1)),
        response(call('preencher_elemento', alvo='campo 2', texto='dois', indice=1)),
        response(text='Nao executei o segundo preenchimento.')],
        [IntentDecision('aprovar', 'primeiro campo'),
         IntentDecision('esclarecer', 'segundo campo incerto', 'Qual outro campo?'),
         IntentDecision('aprovar', 'segundo campo')],
        max_actions=1, use_dispatcher=True)
    case.harness.processar_mensagem('Complete dois campos conforme minha preferencia.')
    waiting = case.harness.current_task()
    assert waiting.state is TaskState.WAITING
    assert case.permission.actions_attempted == 1
    assert len(case.effects) == 1
    case.harness.processar_mensagem('campo 2')
    assert case.harness.current_task().task_id == waiting.task_id
    assert case.permission.actions_attempted >= 1
    assert len(case.effects) == 1
    assert case.harness.current_task().state is TaskState.FAILED


def test_permission_checkpoint_keeps_guard_without_reusing_authorization():
    confirmations = []
    permission = PermissionManager(confirmation_channel=SimpleNamespace(
        confirmar=lambda request: confirmations.append(request) or True))
    assert permission.autorizar('preencher_elemento',
                                {'indice': 1, 'texto': 'primeiro'})[0]
    initial_confirmations = len(confirmations)
    assert permission.last_authorized_action_signature is not None
    permission.registrar_resultado(True, 'preencher_elemento',
                                   {'indice': 1, 'texto': 'primeiro'})
    permission.registrar_fonte_nao_confiavel('ler_pagina')
    saved = permission.checkpoint_limits()
    permission.iniciar_tarefa()
    permission.restore_limits(saved)
    assert permission.actions_attempted == 1
    assert permission.fonte_nao_confiavel_pendente == 'ler_pagina'
    assert permission.last_authorized_action_signature is None
    assert permission.last_authorized_action_tool is None
    assert permission.autorizar('preencher_elemento',
                                {'indice': 2, 'texto': 'segundo'})[0]
    assert len(confirmations) == initial_confirmations + 1
    assert 'conteudo nao confiavel' in confirmations[-1].reason


def test_denied_confirmation_after_wait_prevents_effect(build):
    case = build([
        response(call('obter_contexto_navegador', foco='campo')),
        response(call('preencher_elemento', alvo='campo', texto='valor', indice=1)),
        response(call('preencher_elemento', alvo='campo', texto='valor', indice=1)),
        response(text='Acao negada.')],
        [IntentDecision('esclarecer', 'campo incerto', 'Qual campo devo preencher?'),
         IntentDecision('aprovar', 'campo esclarecido')],
        use_dispatcher=True, confirmation_approved=False)
    case.harness.processar_mensagem('Preencha o campo indicado.')
    waiting = case.harness.current_task()
    assert waiting.state is TaskState.WAITING
    assert case.permission.fonte_nao_confiavel_pendente == 'obter_contexto_navegador'
    case.harness.processar_mensagem('campo 1')
    assert case.harness.current_task().task_id == waiting.task_id
    assert len(case.confirmations) == 1
    assert case.effects == [('obter_contexto_navegador', {'foco': 'campo'})]
    assert case.permission.last_authorized_action_signature is None


@pytest.mark.parametrize('insufficient_answer', ['sim', 'pode ser'])
def test_short_detail_resumes_but_yes_does_not_answer_which_field(build, insufficient_answer):
    case = build([
        response(call('preencher_elemento', alvo='campo pendente', texto='valor', indice=1)),
        response(call('preencher_elemento', alvo='campo 2', texto='valor', indice=2)),
        response(text='Campo preenchido.')],
        [IntentDecision('esclarecer', 'campo incerto', 'Qual campo devo preencher?'),
         IntentDecision('aprovar', 'campo esclarecido')],
        use_dispatcher=True)
    case.harness.processar_mensagem('Preencha o campo indicado.')
    waiting = case.harness.current_task()
    calls_before = len(case.model_inputs)
    _, answer = case.harness.processar_mensagem(insufficient_answer)
    assert answer.output_text == 'Qual campo devo preencher?'
    assert case.harness.current_task().state is TaskState.WAITING
    assert len(case.model_inputs) == calls_before
    case.harness.processar_mensagem('campo 2')
    assert case.harness.current_task().task_id == waiting.task_id
    assert case.harness.current_task().state is TaskState.COMPLETED
    assert [name for name, _ in case.tools] == ['preencher_elemento']


@pytest.mark.parametrize('question', [
    'Em qual pasta devo salvar?',
    'Para onde devo mover o arquivo?',
    'Com qual aplicativo devo abrir?',
])
@pytest.mark.parametrize('answer', ['sim', 'pode ser'])
def test_yes_does_not_supply_requested_location_or_app(build, question, answer):
    case = build([response(call('preencher_elemento', alvo='pendente', texto='valor'))],
        [IntentDecision('esclarecer', 'dado ausente', question)])
    case.harness.processar_mensagem('Execute a acao depois de esclarecer o destino.')
    waiting = case.harness.current_task()
    assert waiting.state is TaskState.WAITING
    model_calls = len(case.model_inputs)
    _, reply = case.harness.processar_mensagem(answer)
    assert reply.output_text == question
    assert case.harness.current_task().task_id == waiting.task_id
    assert case.harness.current_task().state is TaskState.WAITING
    assert len(case.model_inputs) == model_calls


def test_clarification_does_not_renew_model_round_budget(build):
    case = build([response(call('preencher_elemento', alvo='pendente', texto='valor'))],
        [IntentDecision('esclarecer', 'alvo incerto', 'Qual campo devo preencher?')],
        max_model_rounds=1)
    case.harness.processar_mensagem('Preencha o campo indicado.')
    waiting = case.harness.current_task()
    assert waiting.state is TaskState.WAITING
    case.harness.processar_mensagem('campo 1')
    assert case.harness.current_task().task_id == waiting.task_id
    assert case.harness.current_task().state is TaskState.FAILED
    assert len(case.model_inputs) == 1
    assert case.tools == []


def test_successive_questions_share_one_model_round_budget(build):
    case = build([
        response(call('preencher_elemento', alvo='pendente', texto='valor')),
        response(call('preencher_elemento', alvo='esclarecido', texto='valor'))],
        [IntentDecision('esclarecer', 'alvo incerto', 'Qual campo devo preencher?'),
         IntentDecision('esclarecer', 'valor incerto', 'Qual texto devo inserir?')],
        max_model_rounds=2)
    case.harness.processar_mensagem('Preencha o campo indicado.')
    task_id = case.harness.current_task().task_id
    assert case.harness.current_task().state is TaskState.WAITING
    case.harness.processar_mensagem('campo 1')
    assert case.harness.current_task().state is TaskState.WAITING
    case.harness.processar_mensagem('valor')
    assert case.harness.current_task().task_id == task_id
    assert case.harness.current_task().state is TaskState.FAILED
    assert case.harness.current_task().error == 'model_round_limit'
    assert len(case.model_inputs) == 2
    assert case.tools == []


def test_inconclusive_reply_keeps_same_wait_without_model_call(build):
    case = build(google_script(),
        [IntentDecision('aprovar', 'buscar'),
         IntentDecision('esclarecer', 'bloqueio externo', 'Devo verificar novamente?')],
        google_result)
    _, original_question = case.harness.processar_mensagem(GOAL)
    waiting = case.harness.current_task()
    calls_before = len(case.model_inputs)
    _, answer = case.harness.processar_mensagem('talvez')
    assert answer.output_text == original_question.output_text
    assert case.harness.current_task().task_id == waiting.task_id
    assert case.harness.current_task().state is TaskState.WAITING
    assert len(case.model_inputs) == calls_before


def test_cancel_button_closes_waiting_task(build):
    case = build(google_script(),
        [IntentDecision('aprovar', 'buscar'),
         IntentDecision('esclarecer', 'bloqueio externo', 'Devo verificar novamente?')],
        google_result)
    case.harness.processar_mensagem(GOAL)
    task_id = case.harness.current_task().task_id
    assert case.harness.cancel_current_task()
    assert case.harness.task_manager.get_snapshot(task_id).state is TaskState.CANCELLED
    assert case.harness._clarification is None


def test_complete_goal_proposes_opening_result_after_clarification(build):
    """A abertura e proposta depois de observar os links recuperados."""
    contexts = [0]

    def recovered_result(item):
        if item.name == 'obter_contexto_navegador':
            contexts[0] += 1
            if contexts[0] > 1:
                return ToolResult.success('Resultados recuperados', data={
                    'abas': 'Aba ativa: 1\nAba 1: Busca | ' + GOOGLE_SEARCH + ' [ATIVA]',
                    'pagina': ('Links relevantes:\n- texto=Create Aeronautics - '
                               'Minecraft Mods | href=' + RESULT_URL),
                }, tool_name=item.name)
        return google_result(item)

    case = build(google_script()[:2] + [
        response(call('obter_contexto_navegador', foco='resultados')),
        response(text='Create Aeronautics - Minecraft Mods'),
        lambda prompt: response(call('navegar_navegador', url=RESULT_URL))
            if 'abrir_resultado' in str(prompt) else response(text='Resultado descrito.')],
        [IntentDecision('aprovar', 'buscar'),
         IntentDecision('aprovar', 'site escolhido')],
        recovered_result)
    case.harness.processar_mensagem(GOAL)
    case.harness.processar_mensagem('nao, verifique o com maior relevancia')
    assert any(
        (name == 'navegar_navegador' and args.get('url') == RESULT_URL)
        or (name == 'clicar_elemento'
            and args.get('alvo') == 'Create Aeronautics - Minecraft Mods')
        for name, args in case.tools[2:]
    ), ([name for name, _ in case.tools], case.harness.current_task().error)
