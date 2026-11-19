"""Etapa 4: destino observado em navegador inteiramente simulado."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import core.harness_runtime as runtime
from core.harness import AurenHarness
from core.harness_heuristics import _indice_resultado
from core.intent_verification import IntentDecision
from core.permission_manager import PermissionManager
from core.task_manager import TaskManager, TaskState
from core.task_trace import TaskTraceStore
from core.tool_result import ToolResult


SEARCH = 'https://www.google.com/search?q=create+aeronautics'
RESULT = 'https://example.test/create-aeronautics'
GOAL = 'Pesquise Create Aeronautics e abra o resultado mais relevante.'


def call(name, **arguments):
    return SimpleNamespace(type='function_call', name=name,
                           arguments=json.dumps(arguments), call_id=name + str(arguments))


def response(*calls, text=''):
    return SimpleNamespace(output=list(calls), output_text=text, usage=None)


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, 'LOG_DIR', tmp_path / 'logs')
    monkeypatch.setattr(runtime, 'CHAT_LOGS_DIR', tmp_path / 'logs' / 'chats')
    monkeypatch.setattr(runtime, 'TASK_LOG_DIR', tmp_path / 'logs' / 'tarefas')
    monkeypatch.setattr(runtime, 'LOG_FILE', tmp_path / 'logs' / 'auren.log')
    created = []

    def build(answers, *, destination=RESULT, click_ok=True, include_links=True,
              include_context=True, stale_first_destination_read=False,
              search_page=None):
        answers = iter(answers)
        calls, inputs = [], []
        current = {'url': '', 'title': ''}
        stale_read = [False]
        permission = PermissionManager(confirmation_channel=SimpleNamespace(confirmar=lambda _: True))

        def model(prompt, *_args):
            inputs.append(str(prompt))
            answer = next(answers)
            return answer(prompt) if callable(answer) else answer

        def execute(item):
            args = json.loads(item.arguments)
            calls.append((item.name, args))
            if item.name == 'navegar_navegador':
                current['url'] = SEARCH if args['url'] == SEARCH else destination
                current['title'] = ('Pesquisa' if current['url'] == SEARCH
                                    else 'Create Aeronautics - Minecraft Mods')
                if args['url'] != SEARCH:
                    stale_read[0] = stale_first_destination_read
                return ToolResult.success('Naveguei', tool_name=item.name)
            if item.name == 'clicar_elemento':
                if not click_ok:
                    return ToolResult.failure('Clique falhou', tool_name=item.name)
                current['url'] = destination
                current['title'] = 'Create Aeronautics - Minecraft Mods'
                stale_read[0] = stale_first_destination_read
                return ToolResult.success('Cliquei', tool_name=item.name)
            if item.name == 'voltar_pagina':
                current['url'] = 'https://other.test/start'
                current['title'] = 'Outra pagina'
                return ToolResult.success('Voltei', tool_name=item.name)
            if item.name == 'obter_contexto_navegador':
                if not include_context:
                    return ToolResult.success('Sem dados estruturados', tool_name=item.name)
                observed_url = SEARCH if stale_read[0] else current['url']
                observed_title = 'Pesquisa' if stale_read[0] else current['title']
                stale_read[0] = False
                page = ((search_page or
                         ('Links relevantes:\n- texto=Create Aeronautics - Minecraft Mods | '
                          f'href={RESULT}'))
                        if observed_url == SEARCH and include_links else 'Pagina atual')
                tabs = (f"Aba ativa: 1\nAba 1: {observed_title} | "
                        f"{observed_url} [ATIVA]")
                return ToolResult.success('Contexto', data={'abas': tabs, 'pagina': page},
                                          tool_name=item.name)
            raise AssertionError(item.name)

        harness = AurenHarness(
            criar_resposta=model, executar_ferramenta=execute,
            mostrar_uso=lambda: None, obter_chamadas=lambda result: result.output,
            comando_rapido=lambda _: (False, ''), iniciar_tarefa=permission.iniciar_tarefa,
            apos_tarefa=None, fechar=lambda: None,
            verificar_intencao=lambda *_: IntentDecision('aprovar', 'simulado'),
            permission_manager=permission, task_manager=TaskManager(),
            trace_store=TaskTraceStore(tmp_path / f'trace-{len(created)}.sqlite3'),
        )
        created.append(harness)
        return SimpleNamespace(harness=harness, calls=calls, current=current, inputs=inputs)

    yield build
    for harness in created:
        harness._background_queue.shutdown(cancel_pending=True)
        harness._encerrar_sessao_chat('test_closed')


def _sequence(open_call, *, final_text='Site aberto.'):
    return [response(call('navegar_navegador', url=SEARCH)),
            response(call('obter_contexto_navegador', foco='resultados')),
            response(open_call),
            response(call('obter_contexto_navegador', foco='destino')),
            response(text=final_text)]


@pytest.mark.parametrize('open_call', [
    call('clicar_elemento', alvo='Create Aeronautics - Minecraft Mods'),
    call('navegar_navegador', url=RESULT),
])
def test_correct_result_requires_observed_destination(scenario, open_call):
    case = scenario(_sequence(open_call))
    case.harness.processar_mensagem(GOAL)
    assert case.harness.current_task().state is TaskState.COMPLETED, (case.harness.current_task().error, len(case.inputs))
    assert [name for name, _ in case.calls].count('obter_contexto_navegador') == 2


@pytest.mark.parametrize('destination', [SEARCH, 'https://wrong.test/other',
                                        'https://example.test/other'])
def test_successful_click_without_requested_destination_stays_unfinished(scenario, destination):
    case = scenario(_sequence(call('clicar_elemento', alvo='Create Aeronautics - Minecraft Mods'))
                    + [response(text='Ja abri.')], destination=destination)
    case.harness.processar_mensagem(GOAL)
    assert case.harness.current_task().state is TaskState.FAILED


def test_failed_opening_is_not_success(scenario):
    case = scenario(_sequence(call('clicar_elemento', alvo='Create Aeronautics - Minecraft Mods')),
                    click_ok=False)
    case.harness.processar_mensagem(GOAL)
    assert case.harness.current_task().state is TaskState.FAILED


def test_result_redirected_to_google_verification_is_not_opened(scenario):
    case = scenario(_sequence(call('navegar_navegador', url=RESULT)),
                    destination='https://www.google.com/sorry/index')
    case.harness.processar_mensagem(GOAL)
    assert case.harness.current_task().state is TaskState.WAITING
    assert case.harness._browser_destination_state.get('verified') is False
    assert [name for name, _ in case.calls].count('navegar_navegador') == 2


def test_manual_resolution_of_result_challenge_verifies_selected_destination(scenario):
    answers = [response(call('navegar_navegador', url=SEARCH)),
               response(call('obter_contexto_navegador', foco='resultados')),
               response(call('navegar_navegador', url=RESULT)),
               response(call('obter_contexto_navegador', foco='bloqueio')),
               response(call('obter_contexto_navegador', foco='apos verificacao')),
               response(text='Site aberto.')]
    case = scenario(answers, destination='https://www.google.com/sorry/index')
    case.harness.processar_mensagem(GOAL)
    waiting = case.harness.current_task()
    assert waiting.state is TaskState.WAITING
    case.current.update(url=RESULT, title='Create Aeronautics - Minecraft Mods')
    case.harness.processar_mensagem('pronto')
    assert case.harness.current_task().task_id == waiting.task_id
    assert case.harness.current_task().state is TaskState.COMPLETED
    assert case.harness._browser_destination_state.get('verified') is True
    assert [name for name, _ in case.calls].count('navegar_navegador') == 2


def test_same_page_redirect_with_tracking_parameter(scenario):
    case = scenario(_sequence(call('navegar_navegador', url=RESULT)),
                    destination='https://www.example.test/create-aeronautics?utm_source=search')
    case.harness.processar_mensagem(GOAL)
    assert case.harness.current_task().state is TaskState.COMPLETED


def test_text_claim_without_post_observation_is_not_success(scenario):
    case = scenario([response(call('navegar_navegador', url=SEARCH)),
                     response(call('obter_contexto_navegador', foco='resultados')),
                     response(call('clicar_elemento', alvo='Create Aeronautics - Minecraft Mods')),
                     response(text='Ja abri.'), response(text='Ja abri.')])
    case.harness.processar_mensagem(GOAL)
    assert case.harness.current_task().state is TaskState.FAILED


@pytest.mark.parametrize('missing', ['links', 'structured_context'])
def test_missing_pre_action_link_evidence_fails_closed(scenario, missing):
    case = scenario(_sequence(call('navegar_navegador', url=RESULT)),
                    include_links=missing != 'links',
                    include_context=missing != 'structured_context')
    case.harness.processar_mensagem(GOAL)
    assert case.harness.current_task().state is TaskState.FAILED
    assert ('navegar_navegador', {'url': RESULT}) not in case.calls


def test_delayed_observation_can_be_rechecked_without_reopening(scenario):
    answers = [response(call('navegar_navegador', url=SEARCH)),
               response(call('obter_contexto_navegador', foco='resultados')),
               response(call('clicar_elemento', alvo='Create Aeronautics - Minecraft Mods')),
               response(call('obter_contexto_navegador', foco='destino')),
               response(call('obter_contexto_navegador', foco='destino novamente')),
               response(text='Resultado aberto.')]
    case = scenario(answers, stale_first_destination_read=True)
    case.harness.processar_mensagem(GOAL)
    assert case.harness.current_task().state is TaskState.COMPLETED
    assert [name for name, _ in case.calls].count('clicar_elemento') == 1


def test_old_search_context_cannot_authorize_open_after_page_change(scenario):
    answers = [response(call('navegar_navegador', url=SEARCH)),
               response(call('obter_contexto_navegador', foco='resultados')),
               response(call('voltar_pagina')),
               response(call('navegar_navegador', url=RESULT)),
               response(call('obter_contexto_navegador', foco='destino')),
               response(text='Site aberto.')]
    case = scenario(answers)
    case.harness.processar_mensagem(GOAL)
    assert case.harness.current_task().state is TaskState.FAILED
    assert ('navegar_navegador', {'url': RESULT}) not in case.calls


def test_new_browser_read_invalidates_old_search_links(scenario):
    def observe_other_page(_prompt):
        case.current.update(url='https://other.test/start', title='Outra pagina')
        return response(call('obter_contexto_navegador', foco='pagina atual'))

    case = scenario([response(call('navegar_navegador', url=SEARCH)),
                     response(call('obter_contexto_navegador', foco='resultados')),
                     observe_other_page,
                     response(call('navegar_navegador', url=RESULT)),
                     response(text='Site aberto.')])
    case.harness.processar_mensagem(GOAL)
    assert case.harness.current_task().state is TaskState.FAILED
    assert ('navegar_navegador', {'url': RESULT}) not in case.calls


def test_clarification_resumes_same_task_and_verifies_destination(scenario):
    case = scenario([response(call('navegar_navegador', url=SEARCH)),
                     response(call('obter_contexto_navegador', foco='resultados')),
                     response(text='Qual resultado devo abrir?'),
                     response(call('clicar_elemento', alvo='Create Aeronautics - Minecraft Mods')),
                     response(call('obter_contexto_navegador', foco='destino')),
                     response(text='Resultado aberto.')])
    case.harness.processar_mensagem(GOAL)
    waiting = case.harness.current_task()
    assert waiting.state is TaskState.WAITING, (waiting.error, len(case.inputs), [name for name, _ in case.calls])
    case.harness.processar_mensagem('o primeiro')
    assert case.harness.current_task().task_id == waiting.task_id
    assert case.harness.current_task().state is TaskState.COMPLETED


def test_search_only_does_not_require_result_destination(scenario):
    case = scenario([response(call('navegar_navegador', url=SEARCH)),
                     response(text='Pesquisa aberta.')])
    case.harness.processar_mensagem('Pesquise Create Aeronautics.')
    assert case.harness.current_task().state is TaskState.COMPLETED


def test_clarification_choice_overrides_original_result_rank():
    objective = ('Pesquise Auren e abra o primeiro resultado.\n'
                 'Pergunta pendente do Auren: Qual resultado devo abrir?\n'
                 'Esclarecimento do usuario: o segundo')
    assert _indice_resultado(objective) == 2
    assert _indice_resultado(objective.replace('o segundo', 'sim')) == 1


def test_most_relevant_does_not_mean_first_result():
    assert _indice_resultado('Pesquise Create Aeronautics e entre no site mais relevante.') is None
    assert _indice_resultado('Pesquise Create Aeronautics e abra o primeiro resultado.') == 1


def test_most_relevant_can_open_observed_nonfirst_result(scenario):
    second = 'https://modrinth.test/mod/create-aeronautics'
    search_page = (
        'Links relevantes:\n'
        '- texto=Create Aeronautics - Minecraft Mods | href=' + second + '\n'
        'Candidatos de link na ordem da pagina:\n'
        '- posicao=1 | texto=Outra pagina | href=https://other.test/page\n'
        '- posicao=2 | texto=Create Aeronautics - Minecraft Mods | href=' + second
    )
    case = scenario(_sequence(call('navegar_navegador', url=second)),
                    destination=second, search_page=search_page)
    case.harness.processar_mensagem(GOAL)
    assert case.harness.current_task().state is TaskState.COMPLETED
    assert ('navegar_navegador', {'url': second}) in case.calls
    assert case.harness._browser_destination_state['verified'] is True


def test_repeated_unverifiable_result_stops_before_model_round_limit(scenario):
    answers = [response(call('navegar_navegador', url=SEARCH)),
               response(call('obter_contexto_navegador', foco='resultados'))]
    for _ in range(6):
        answers.extend((response(call('navegar_navegador', url=RESULT)),
                        response(call('obter_contexto_navegador', foco='resultados'))))
    case = scenario(answers, include_links=False)
    case.harness.processar_mensagem(GOAL)
    task = case.harness.current_task()
    assert task.state is TaskState.FAILED
    assert task.error == 'browser_result_no_progress'
    assert [name for name, _ in case.calls].count('navegar_navegador') == 1
    assert len(case.inputs) < case.harness._task_round_limit
