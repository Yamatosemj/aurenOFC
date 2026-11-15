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
            return next(answers)

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
    if item.name == 'navegar_navegador':
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
    assert case.reviews[-1][1] == ['clicar_elemento']
    assert any(name == 'TASK_WAITING' and data['task_id'] == task.task_id
               for name, data in case.events)


def test_answer_resumes_same_id_and_preserves_google_evidence(build):
    case = build(google_script() + [
        response(call('ler_pagina', foco='resultado mais relevante')),
        response(text='Create Aeronautics - Minecraft Mods')],
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
    assert [name for name, _ in case.tools].count('ler_pagina') == 1


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


def test_agora_abre_spotify_replaces_waiting_task(build):
    case = build(google_script() + [response(text='Novo pedido recebido.')],
        [IntentDecision('aprovar', 'buscar'),
         IntentDecision('esclarecer', 'bloqueio externo', 'Devo verificar novamente?')],
        google_result)
    case.harness.processar_mensagem(GOAL)
    old = case.harness.current_task()
    case.harness.processar_mensagem('agora abre o Spotify')
    assert case.harness.task_manager.get_snapshot(old.task_id).state is TaskState.CANCELLED
    assert case.harness.current_task().task_id != old.task_id
    assert case.harness.current_task().objective == 'agora abre o Spotify'


@pytest.mark.parametrize('question,answer', [
    ('Qual resultado devo abrir?', 'quero o segundo'),
    ('Qual resultado devo abrir?', 'abre o primeiro'),
    ('Qual navegador você quer usar?', 'quero o Chrome'),
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
def test_short_yes_resumes_only_yes_no_question_without_repeating_steps(build, answer):
    case = build(google_script() + [
        response(call('ler_pagina', foco='resultado mais relevante')),
        response(text='Create Aeronautics - Minecraft Mods')],
        [IntentDecision('aprovar', 'buscar'),
         IntentDecision('esclarecer', 'bloqueio externo', 'Devo verificar novamente?')],
        google_result)
    case.harness.processar_mensagem(GOAL)
    old = case.harness.current_task()
    case.harness.processar_mensagem(answer)
    assert case.harness.current_task().task_id == old.task_id
    assert [name for name, _ in case.tools] == [
        'navegar_navegador', 'obter_contexto_navegador', 'ler_pagina']


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
    case.harness.processar_mensagem(GOAL)
    waiting = case.harness.current_task()
    calls_before = len(case.model_inputs)
    _, answer = case.harness.processar_mensagem('talvez')
    assert answer.output_text == 'Devo verificar novamente?'
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


@pytest.mark.xfail(strict=True, reason='Etapa 3: resultado encontrado ainda nao e aberto')
def test_complete_goal_still_requires_opening_result(build):
    """Stage 1 sentinel: remains failing until later goal-completion work."""
    case = build(google_script() + [
        response(call('ler_pagina', foco='resultado mais relevante')),
        response(text='Create Aeronautics - Minecraft Mods')],
        [IntentDecision('aprovar', 'buscar'),
         IntentDecision('esclarecer', 'bloqueio externo', 'Devo verificar novamente?')],
        google_result)
    case.harness.processar_mensagem(GOAL)
    case.harness.processar_mensagem('nao, verifique o com maior relevancia')
    assert any(
        (name == 'navegar_navegador' and args.get('url') == RESULT_URL)
        or (name == 'clicar_elemento'
            and args.get('alvo') == 'Create Aeronautics - Minecraft Mods')
        for name, args in case.tools[2:]
    )
