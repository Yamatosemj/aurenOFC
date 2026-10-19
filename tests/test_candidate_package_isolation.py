"""Real source archive creation in a fixture Git repo, without credentials."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile


def test_archive_has_own_pytest_config_and_excludes_runtime_data(tmp_path):
    source = Path(__file__).resolve().parents[1]
    root = tmp_path/'source'
    builder = root/'scripts/diagnosticos/empacotar_candidata.py'
    builder.parent.mkdir(parents=True)
    shutil.copyfile(source/'scripts/diagnosticos/empacotar_candidata.py', builder)
    fixture_files = {
        'pytest.ini': '[pytest]\ntestpaths = tests\n',
        'auren.py': '# fixture, no runtime initialization\n',
        'requirements.txt': '# fixture\n',
        'tests/test_fixture.py': 'def test_fixture(): assert True\n',
        '.env': 'FIXTURE_SECRET=not-a-real-secret\n',
        'data/private.txt': 'synthetic runtime data',
        'logs/private.txt': 'synthetic log',
        'browser_profile/private.txt': 'synthetic browser state',
        'desktop/private.txt': 'excluded desktop fixture',
    }
    for name, content in fixture_files.items():
        path = root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    def git(*args):
        return subprocess.run(['git', *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
    git('init')
    git('add', '-A')
    git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'fixture')
    archive = tmp_path/'candidate.zip'
    subprocess.run([sys.executable, str(builder), '--output', str(archive)], cwd=root,
                   check=True, capture_output=True, text=True, timeout=15)
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        assert 'AUREN_CANDIDATA/pytest.ini' in names
        assert all(not any(part in {'.git', '.env', 'data', 'logs', 'browser_profile', 'desktop'}
                           for part in Path(name).parts) for name in names)
        manifest = json.loads(bundle.read('AUREN_CANDIDATA/MANIFESTO.json'))
        assert manifest['source_commit'] == git('rev-parse', 'HEAD')
        for name, digest in manifest['sha256'].items():
            assert hashlib.sha256(bundle.read('AUREN_CANDIDATA/'+name)).hexdigest() == digest
