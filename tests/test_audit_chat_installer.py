import json
import base64
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(os.name != 'nt', reason='instalador PowerShell Windows')
ROOT = Path(__file__).resolve().parents[1]
BLOB = '52abfd109c06cdc458727337579984d91da879bc'


def fixture(tmp_path):
    root = tmp_path / 'source'
    script = root / 'scripts' / 'instalar' / 'AUTORIZAR_TESTES_CHAT.ps1'
    script.parent.mkdir(parents=True)
    original = ROOT / 'scripts' / 'instalar' / script.name
    shutil.copyfile(original, script)
    source = root / 'remote_tests' / 'chat-control-functions.ps1'
    source.parent.mkdir()
    shutil.copyfile(ROOT / 'remote_tests' / source.name, source)
    profile = tmp_path / 'fictional-profile'
    policy = profile / 'auren-remote' / 'policy'
    policy.mkdir(parents=True)
    old = re.search(r"\$oldBlock = @'\n(.*?)\n'@", original.read_text(encoding='utf-8'), re.S).group(1)
    (policy / 'before-job.ps1').write_text(old, encoding='utf-8')
    (policy / 'remote-control-functions.ps1').write_text('# fictional legacy policy')
    (policy / 'control-approval.json').write_text('{}')
    env = dict(os.environ, USERPROFILE=str(profile))
    return script, policy, env


def run(script, env, *args):
    # Executa o texto revisado na sandbox sem mudar ExecutionPolicy.
    directory = "'" + str(script.parent).replace("'", "''") + "'"
    body = script.read_text(encoding='utf-8').replace('$PSScriptRoot', directory)
    command = '& {\n' + body + '\n} ' + ' '.join(args)
    encoded = base64.b64encode(command.encode('utf-16-le')).decode('ascii')
    return subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand',
                           encoded], env=env, capture_output=True, timeout=15)


def test_aud033_missing_explicit_opt_in_changes_nothing(tmp_path):
    script, policy, env = fixture(tmp_path)
    before = {p.name: p.read_bytes() for p in policy.iterdir()}
    result = run(script, env)
    assert result.returncode != 0
    assert {p.name: p.read_bytes() for p in policy.iterdir()} == before


def test_aud033_explicit_offline_install_writes_consistent_approval(tmp_path):
    script, policy, env = fixture(tmp_path)
    result = run(script, env, '-AutorizarValidacaoOffline')
    assert result.returncode == 0, result.stderr
    approval = json.loads((policy / 'chat-control-approval.json').read_text(encoding='utf-8'))
    assert approval['offline_hosted_validation'] is True
    assert approval['enabled'] is True and approval['workflow_blob'] == BLOB
    assert 'Test-RemoteControlRequest' in (policy / 'before-job.ps1').read_text()
    assert (policy / 'before-job.pre-chat.bak').exists()


def test_aud033_incomplete_previous_install_does_not_claim_success(tmp_path):
    script, policy, env = fixture(tmp_path)
    (policy / 'before-job.ps1').write_text('Test-ChatControlRequest')
    (policy / 'chat-control-functions.ps1').write_text('offline_hosted_validation')
    (policy / 'chat-control-approval.json').write_text(json.dumps({'enabled': True, 'workflow_blob': BLOB}))
    before = {p.name: p.read_bytes() for p in policy.iterdir()}
    assert run(script, env, '-AutorizarValidacaoOffline').returncode != 0
    assert {p.name: p.read_bytes() for p in policy.iterdir()} == before
