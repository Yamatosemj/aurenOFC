"""Objetivos compostos com modelo e navegador inteiramente simulados."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import core.harness_runtime as runtime
from core.harness import AurenHarness
from core.intent_verification import IntentDecision
from core.permission_manager import PermissionManager
from core.task_manager import TaskManager, TaskState
from core.task_trace import TaskTraceStore
from core.tool_result import ToolResult


SEARCH_URL = 'https://www.google.com/search?q=create+aeronautics'
RESULT_URL = 'https://example.test/create-aeronautics'


def _call(name, **args):
    return SimpleNamespace(type='function_call', name=name,
                           arguments=json.dumps(args), call_id=name + str(args))


def _response(*calls, text=''):
    return SimpleNamespace(output=list(calls), output_text=text, usage=None)


@pytest.fixture
def run_goal(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, 'LOG_DIR', tmp_path / 'logs')
    monkeypatch.setattr(runtime, 'CHAT_LOGS_DIR', tmp_path / 'logs' / 'chats')
    monkeypatch.setattr(runtime, 'TASK_LOG_DIR', tmp_path / 'logs' / 'tarefas')
    monkeypatch.setattr(runtime, 'LOG_FILE', tmp_path / 'logs' / 'auren.log')
    opened = []

    def run(goal, answers, *, fail_result=False):
        answers = iter(answers)
        tools, inputs = [], []
        browser = {'url': '', 'title': ''}
        permission = PermissionManager(confirmation_channel=SimpleNamespace(confirmar=lambda _: True))

        def model(prompt, *_args):
            inputs.append(str(prompt))
            answer = next(answers)
            return answer(prompt) if callable(answer) else answer

        def execute(item):
            args = json.loads(item.arguments)
            tools.append((item.name, args))
            if fail_result and args.get('url') == RESULT_URL:
                return ToolResult.failure('Abertura simulada falhou',
                                          error_code='simulated_failure', tool_name=item.name)
            if item.name == 'navegar_navegador':
                browser['url'] = args['url']
                browser['title'] = ('Pesquisa' if 'google.com/search' in args['url']
                                    else 'Create Aeronautics - Minecraft Mods')
            if item.name == 'obter_contexto_navegador':
                result_url = ('https://example.test/receitas' if 'receitas' in browser['url']
                              else RESULT_URL)
                title = ('Receitas' if 'receitas' in browser['url']
                         else 'Create Aeronautics - Minecraft Mods')
                page = (f'Links relevantes:\n- texto={title} | href={result_url}'
                        if 'google.com/search' in browser['url'] else 'Pagina atual')
                return ToolResult.success('Contexto simulado', data={
                    'abas': (f"Aba ativa: 1\nAba 1: {browser['title']} | "
                             f"{browser['url']} [ATIVA]"), 'pagina': page,
                }, tool_name=item.name)
            return ToolResult.success('Resultado simulado', tool_name=item.name)

        harness = AurenHarness(
            criar_resposta=model, executar_ferramenta=execute,
            mostrar_uso=lambda: None, obter_chamadas=lambda result: result.output,
            comando_rapido=lambda _: (False, ''), iniciar_tarefa=permission.iniciar_tarefa,
            apos_tarefa=None, fechar=lambda: None,
            verificar_intencao=lambda *_: IntentDecision('aprovar', 'acao permitida'),
            permission_manager=permission, task_manager=TaskManager(),
            trace_store=TaskTraceStore(tmp_path / ('trace-' + str(len(opened)) + '.sqlite3')),
        )
        opened.append(harness)
        _, reply = harness.processar_mensagem(goal)
        return SimpleNamespace(harness=harness, reply=reply, tools=tools, inputs=inputs)

    yield run
    for harness in opened:
        harness._background_queue.shutdown(cancel_pending=True)
        harness._encerrar_sessao_chat('test_closed')


def _open_after_obligation(prompt):
    assert 'abrir_resultado' in str(prompt)
    return _response(_call('navegar_navegador', url=RESULT_URL))


@pytest.mark.parametrize('goal', [
    'Pesquise Create Aeronautics e abra o site mais relevante.',
    'Perfeito Auren, agora pesquise Create Aeronautics e entre no primeiro resultado relevante.',
])
def test_search_then_open_result_executes_second_action(run_goal, goal):
    case = run_goal(goal, [
        _response(_call('navegar_navegador', url=SEARCH_URL)),
        _response(_call('obter_contexto_navegador', foco='resultados')),
        _response(text='Create Aeronautics - Minecraft Mods: ' + RESULT_URL),
        _open_after_obligation,
        _response(_call('obter_contexto_navegador', foco='destino')),
        _response(text='Site aberto.'),
    ])
    assert case.harness.current_task().state is TaskState.COMPLETED
    assert [args['url'] for name, args in case.tools if name == 'navegar_navegador'] == [
        SEARCH_URL, RESULT_URL]


def test_open_browser_search_recipes_then_open_result(run_goal):
    case = run_goal('Abra o navegador, pesquise receitas e entre no primeiro resultado.', [
        _response(_call('navegar_navegador', url='https://example.test/start')),
        _response(_call('obter_contexto_navegador', foco='aba')),
        _response(_call('navegar_navegador', url='https://www.google.com/search?q=receitas')),
        _response(_call('obter_contexto_navegador', foco='resultados')),
        _response(text='Primeiro resultado: https://example.test/receitas'),
        lambda prompt: _response(_call('navegar_navegador', url='https://example.test/receitas'))
            if 'abrir_resultado' in str(prompt) else _response(text='Primeiro resultado encontrado.'),
        _response(_call('obter_contexto_navegador', foco='destino')),
        _response(text='Site aberto.'),
    ])
    assert case.harness.current_task().state is TaskState.COMPLETED
    assert [args['url'] for name, args in case.tools if name == 'navegar_navegador'] == [
        'https://example.test/start', 'https://www.google.com/search?q=receitas',
        'https://example.test/receitas',
    ]


def test_price_query_does_not_open_result(run_goal):
    case = run_goal('Pesquise Hollow Knight e me diga o preço.', [
        _response(_call('navegar_navegador', url='https://www.google.com/search?q=Hollow+Knight+preco')),
        _response(text='O preço encontrado é R$ 39,90.'),
    ])
    assert case.harness.current_task().state is TaskState.COMPLETED
    assert len(case.tools) == 1


def test_search_only_does_not_open_result(run_goal):
    case = run_goal('Pesquise Create Aeronautics.', [
        _response(_call('navegar_navegador', url=SEARCH_URL)),
        _response(text='Pesquisa aberta.'),
    ])
    assert case.harness.current_task().state is TaskState.COMPLETED
    assert len(case.tools) == 1


def test_repeated_text_without_opening_result_fails_safely(run_goal):
    case = run_goal('Pesquise Create Aeronautics e abra o site mais relevante.', [
        _response(_call('navegar_navegador', url=SEARCH_URL)),
        _response(_call('obter_contexto_navegador', foco='resultados')),
        _response(text='Encontrei o site.'),
        lambda prompt: _response(text='Encontrei o site.')
            if 'abrir_resultado' in str(prompt) else _response(text='Sem acao.'),
    ])
    assert case.harness.current_task().state is TaskState.FAILED
    assert case.harness.current_task().error == 'composite_action_pending'
    assert [name for name, _ in case.tools] == [
        'navegar_navegador', 'obter_contexto_navegador']


def test_failed_opening_is_not_reported_as_completed(run_goal):
    case = run_goal('Pesquise Create Aeronautics e abra o site mais relevante.', [
        _response(_call('navegar_navegador', url=SEARCH_URL)),
        _response(_call('obter_contexto_navegador', foco='resultados')),
        _response(text='Encontrei o site.'),
        _open_after_obligation,
        _response(text='Nao consegui abrir.'),
    ], fail_result=True)
    assert case.harness.current_task().state is TaskState.FAILED
    assert [args['url'] for name, args in case.tools if name == 'navegar_navegador'] == [
        SEARCH_URL, RESULT_URL]


def test_question_after_search_waits_and_resumes_same_task(run_goal):
    case = run_goal('Pesquise Create Aeronautics e abra o resultado escolhido.', [
        _response(_call('navegar_navegador', url=SEARCH_URL)),
        _response(_call('obter_contexto_navegador', foco='resultados')),
        _response(text='Qual resultado devo abrir?'),
        _response(_call('navegar_navegador', url=RESULT_URL)),
        _response(_call('obter_contexto_navegador', foco='destino')),
        _response(text='Resultado aberto.'),
    ])
    waiting = case.harness.current_task()
    assert waiting.state is TaskState.WAITING
    assert case.reply.output_text == 'Qual resultado devo abrir?'
    case.harness.processar_mensagem('o primeiro')
    assert case.harness.current_task().task_id == waiting.task_id
    assert case.harness.current_task().state is TaskState.COMPLETED
    assert [args['url'] for name, args in case.tools if name == 'navegar_navegador'] == [
        SEARCH_URL, RESULT_URL]
