"""Evidence is persisted state and exact temporary effects, not model prose."""
import json
from pathlib import Path
import subprocess
import sys


def child(mode, directory):
    return subprocess.run([sys.executable, '-B', '-m', 'remote_tests.phase5_checkpoint_fixture', mode, str(directory)],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=20)


def test_sixteen_step_goal_resumes_in_another_process_without_duplicate_effects(tmp_path):
    directory=tmp_path/'long-goal'
    first=child('first', directory)
    assert first.returncode == 17, first.stderr
    before=json.loads((directory/'first.json').read_text())
    assert before['state']=='paused' and before['steps']==8
    resumed=child('resume', directory)
    assert resumed.returncode == 0, resumed.stderr
    after=json.loads((directory/'resume.json').read_text())
    assert after['state']=='completed' and after['task_id']==before['task_id']
    assert after['steps']==16 and after['observations']==[str(i) for i in range(1,17)]
    assert before['model_calls'] < after['model_calls'] <= before['model_limit']==after['model_limit']


def test_process_death_after_effect_cannot_replay_or_forge_success(tmp_path):
    directory=tmp_path/'uncertain-goal'
    first=child('uncertain', directory)
    assert first.returncode == 21, first.stderr
    before=(directory/'observations.txt').read_bytes()
    resumed=child('refuse_uncertain', directory)
    assert resumed.returncode == 0, resumed.stderr
    after=json.loads((directory/'refuse_uncertain.json').read_text())
    assert after['state']=='interrupted' and after['steps']==1
    expected = b'1\r\n' if sys.platform == 'win32' else b'1\n'
    assert (directory/'observations.txt').read_bytes() == before == expected
