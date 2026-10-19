"""Build source-only candidate archive from an unchanged tracked worktree."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

INSTRUCTIONS = '''AUREN - CANDIDATA ISOLADA, VALIDACAO OFFLINE

Extraia em pasta nova. Este pacote nao instala nem sobrescreve o Auren atual.
Nao inclui credenciais, memoria, logs, perfil de navegador, Electron ou Python.
Requer Python 3.13 e as dependencias ja instaladas; nao baixa nada automaticamente.
Use um ambiente exclusivo da candidata. Nao instale dependencias no Python global.
Confira requirements.txt; a bateria offline tambem precisa de pytest==9.1.1.
O pacote inclui pytest.ini para nao herdar configuracao de outra instalacao.

Na pasta AUREN_CANDIDATA, execute (ou use o caminho do seu python.exe):

python scripts/diagnosticos/offline_python.py -m pytest -q tests/test_application_discovery_latency.py tests/test_usability_router.py tests/test_sqlite_connection_lifecycle.py tests/test_task_persistence_cost.py tests/test_usability_recovery.py tests/test_chrome_progress_delivery.py tests/test_current_task_evidence.py tests/test_offline_browser_usability.py

Para repetir as medicoes locais, sem modelo real:
python scripts/diagnosticos/offline_python.py scripts/diagnosticos/benchmark_usabilidade.py --samples 100 --output reports/avaliacao.json
python scripts/diagnosticos/offline_python.py scripts/diagnosticos/benchmark_persistencia.py --output reports/persistencia.json

Se py -3 nao encontrar Python, use o caminho completo do python.exe instalado.
Nao mude credenciais, configuracoes globais ou instalacao atual para este teste.

Os testes substituem o modelo e efeitos Windows. O Chromium, quando disponivel,
usa perfil novo e paginas ficticias interceptadas, sem sites externos.
A suite completa deve ser executada no checkout Git: este pacote minimo omite
workflows e documentos historicos necessarios a verificadores estaticos antigos.

Nao execute scripts Live ou envie pedidos ao modelo real nesta etapa.
A avaliacao posterior no Chrome exige nova autorizacao explicita para API.
O lancador preservado e scripts/iniciar/AUREN_CHROME.bat, para essa etapa posterior.
Esta candidata ainda nao foi aprovada para uso diario.

Compare o commit e hashes em MANIFESTO.json com a PR de entrega.
Relatorio completo: docs/estabilizacao/USABILIDADE_OFFLINE.md no repositorio.
Continuacao da validacao: docs/estabilizacao/VALIDACAO_165.md no repositorio.
'''

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    subprocess.run(['git', 'diff', '--exit-code', 'HEAD', '--'], cwd=root, check=True, capture_output=True)
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    files = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode('utf-8').split('\0')
    packages = ('agent/', 'core/', 'memory/', 'providers/', 'tools/', 'skills/', 'ui/', 'tests/')
    scripts = ('scripts/iniciar/', 'scripts/lib/', 'scripts/diagnosticos/')
    roots = {'auren.py', 'config.py', 'main.py', 'interface_auren.py', 'requirements.txt', 'pytest.ini', 'LICENSE_ARIVC_MIT.txt'}
    hashes = {}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in files:
            path = Path(name)
            include = (name in roots or
                (name.startswith(packages) and path.suffix in {'.py', '.html', '.js', '.txt'}) or
                (name.startswith(scripts) and path.suffix in {'.py', '.bat', '.cmd'}))
            if not include:
                continue
            data = (root/path).read_bytes()
            archive.writestr('AUREN_CANDIDATA/'+name, data)
            hashes[name] = hashlib.sha256(data).hexdigest()
        archive.writestr('AUREN_CANDIDATA/LEIA_PRIMEIRO.txt', INSTRUCTIONS)
        archive.writestr('AUREN_CANDIDATA/MANIFESTO.json', json.dumps(
            {'source_commit': sha, 'base_pr': 164, 'validation': 'offline_only', 'sha256': hashes}, indent=2))
    print(json.dumps({'archive': str(args.output), 'source_commit': sha, 'files': len(hashes)}))

if __name__ == '__main__':
    main()
