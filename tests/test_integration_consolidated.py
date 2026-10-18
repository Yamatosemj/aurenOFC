"""Real application composition in a separate source-only synthetic profile."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys

import pytest


@pytest.mark.parametrize('scenario', ['restart', 'denial', 'routines', 'corrupt_database'])
def test_consolidated_application_through_local_http(tmp_path, scenario):
    source = Path(__file__).resolve().parents[1]
    clone = tmp_path/'source'
    clone.mkdir()
    # Explicit source packages only: never copy data, .env, logs or browser profiles.
    for name in ['auren.py', 'config.py']:
        shutil.copyfile(source/name, clone/name)
    for name in ['core', 'agent', 'providers', 'tools', 'memory', 'skills', 'ui', 'remote_tests']:
        for original in (source/name).rglob('*'):
            if original.is_file() and original.suffix in {'.py', '.md', '.html', '.js', '.json'}:
                target = clone/original.relative_to(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(original, target)
    profile = tmp_path/'profile'
    temp = tmp_path/'temp'
    for folder in [profile, temp, profile/'Documents', profile/'AppData', profile/'LocalAppData']:
        folder.mkdir(parents=True, exist_ok=True)
    env = {k:v for k,v in os.environ.items() if k.upper() in {
        'PATH', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'SYSTEMDRIVE', 'PATHEXT', 'OS', 'PROCESSOR_ARCHITECTURE'}}
    env.update(USERPROFILE=str(profile), HOME=str(profile), APPDATA=str(profile/'AppData'),
        LOCALAPPDATA=str(profile/'LocalAppData'), TEMP=str(temp), TMP=str(temp),
        PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    child = subprocess.run([sys.executable, '-B', '-m', 'remote_tests.integration_fixture',
        scenario, str(tmp_path/'result.json')], cwd=clone, env=env,
        capture_output=True, text=True, encoding='utf-8', timeout=35)
    assert child.returncode == 0, child.stdout[-4000:] + child.stderr[-4000:]
    result = json.loads((tmp_path/'result.json').read_text(encoding='utf-8'))
    assert result['scenario'] == scenario and result['checks']
    assert result['real_api_calls'] == 0
