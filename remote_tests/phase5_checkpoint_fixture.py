"""Synthetic process-restart fixture; never imports the real app composition."""
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

from core.harness import AurenHarness
from core.permission_manager import PermissionManager
from core.task_manager import TaskManager
from core.tool_result import ToolResult
from tools import dispatcher


def main():
    mode, directory = sys.argv[1:3]
    directory = Path(directory).resolve()
    if mode in {'first', 'uncertain'}:
        directory.mkdir(parents=False, exist_ok=False)
        (directory/'fixture.marker').write_text('auren-phase5-synthetic-v1', encoding='utf-8')
    elif (directory/'fixture.marker').read_text(encoding='utf-8') != 'auren-phase5-synthetic-v1':
        raise RuntimeError('Not a synthetic fixture directory')
    manager = TaskManager(db_path=directory/'goals.sqlite3')
    pm = PermissionManager()
    objective = '; '.join(f'Consulte o estado ficticio {i}' for i in range(1, 17))
    observation_file = directory/'observations.txt'
    def effect(args, store, context):
        index = len(manager.current_snapshot().steps)
        with observation_file.open('a', encoding='utf-8') as output:
            output.write(str(index)+'\n')
        if mode == 'uncertain':
            os._exit(21)
        if mode == 'first' and index == 8:
            harness.pause_current_task()
        return ToolResult.success(f'Observacao ficticia {index}')
    def provider(*_):
        task = manager.current_snapshot()
        if len(task.steps) >= 16:
            return SimpleNamespace(output=[], output_text='As 16 observacoes foram conferidas.', usage=None)
        name = 'definir_volume_windows' if mode == 'uncertain' else 'obter_status_windows'
        args = '{"percentual":35}' if mode == 'uncertain' else '{}'
        return SimpleNamespace(output=[SimpleNamespace(type='function_call', name=name,
            arguments=args, call_id=f'call-{len(task.steps)+1}')], output_text='', usage=None)
    def verify(snapshot):
        assert observation_file.read_text().splitlines() == [str(i) for i in range(1, 17)]
        return {'summary':'16 observacoes ficticias verificadas', 'steps':[
            {'index': i, 'status':'verified', 'evidence':[i]} for i in range(1,17)]}
    dispatcher.TOOL_HANDLERS['obter_status_windows'] = effect
    dispatcher.TOOL_HANDLERS['definir_volume_windows'] = effect
    harness = AurenHarness(task_manager=manager, permission_manager=pm,
        criar_resposta=provider, obter_chamadas=lambda r:r.output,
        executar_ferramenta=lambda call:dispatcher.executar_ferramenta(call, pm, None),
        mostrar_uso=lambda:None, comando_rapido=lambda _: (False,''), iniciar_tarefa=pm.iniciar_tarefa,
        apos_tarefa=None, fechar=lambda:None, verificar_conclusao=verify, max_model_rounds=30)
    if mode == 'resume':
        task = manager.current_snapshot()
        harness.retomar_tarefa(task.task_id, chat_id=task.chat_id)
    elif mode == 'refuse_uncertain':
        task = manager.current_snapshot()
        try:
            harness.retomar_tarefa(task.task_id, chat_id=task.chat_id)
        except RuntimeError:
            assert task.steps[-1].success is None
        else:
            raise AssertionError('Uncertain effect was resumed')
    else:
        harness.processar_mensagem('Defina o volume para 35.' if mode == 'uncertain' else objective)
    task = manager.current_snapshot()
    result = {'task_id':task.task_id,'state':task.state.value,'steps':len(task.steps),
              'model_calls':task.model_calls,'model_limit':task.model_limit,
              'observations':observation_file.read_text().splitlines()}
    (directory/(mode+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
    if mode == 'first':
        assert task.state.value == 'paused'
        os._exit(17)  # No normal shutdown: SQLite and OS lock must recover.
    harness.shutdown()


if __name__ == '__main__':
    main()
