"""Retenção local explícita: simula por padrão e só remove com confirmação.

Uso, com o Auren encerrado: python -m core.retention --raiz CAMINHO
Acrescente --aplicar somente depois de revisar a simulação.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3


PRAZOS_DIAS = {'conversas': 30, 'estrategias': 90, 'rastros': 30,
               'registros': 30, 'capturas': 7}


def _contido(root: Path, path: Path) -> bool:
    if not path.resolve().is_relative_to(root):
        return False
    current = path
    while current != root:
        if current.is_symlink() or current.is_junction():
            return False
        current = current.parent
    return True


def aplicar_retencao(raiz: str | Path, *, confirmar: bool = False,
                    agora: datetime | None = None) -> dict:
    """Aplica prazos às classes conhecidas; fatos salvos não expiram.

    Sem confirmação, apenas conta os candidatos. Não promete apagar backups,
    cópias sincronizadas ou recuperar dados já removidos.
    """
    root = Path(raiz).resolve(strict=True)
    if not isinstance(confirmar, bool):
        raise ValueError('A confirmação precisa ser um valor booleano explícito.')
    if not root.is_dir():
        raise ValueError('Informe a pasta do projeto.')
    now = agora or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('O horário precisa informar o fuso.')
    counts = {name: 0 for name in PRAZOS_DIAS}
    rejected = 0
    databases = (
        ('data/memory/auren_memory.sqlite3', (('conversas', 'criado_em', 'conversas'),
                                             ('estrategias', 'atualizado_em', 'estrategias'))),
        ('data/traces/auren_trace.sqlite3', (('task_traces', 'finished_at', 'rastros'),)),
    )
    for relative, tables in databases:
        path = root / relative
        if not _contido(root, path):
            rejected += 1
            continue
        if not path.is_file():
            continue
        # A simulação não abre conexão de escrita nem cria banco ausente.
        uri = path.as_uri() + ('?mode=rw' if confirmar else '?mode=ro')
        with sqlite3.connect(uri, uri=True) as connection:
            existing = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table, column, category in tables:
                if table not in existing:
                    continue
                cutoff = (now - timedelta(days=PRAZOS_DIAS[category])).isoformat()
                where = f'julianday({column}) < julianday(?)'
                counts[category] = connection.execute(f'SELECT count(*) FROM {table} WHERE {where}', (cutoff,)).fetchone()[0]
                if confirmar:
                    if table == 'task_traces' and 'task_trace_spans' in existing:
                        connection.execute(f'DELETE FROM task_trace_spans WHERE task_id IN '
                                           f'(SELECT task_id FROM task_traces WHERE {where})', (cutoff,))
                    connection.execute(f'DELETE FROM {table} WHERE {where}', (cutoff,))
    for relative, patterns, category in (
        ('logs', ('*.log', '*.txt'), 'registros'),
        ('runtime/screenshots', ('screen_*.png',), 'capturas'),
    ):
        directory = root / relative
        if not _contido(root, directory):
            rejected += 1
            continue
        if not directory.is_dir():
            continue
        cutoff = (now - timedelta(days=PRAZOS_DIAS[category])).timestamp()
        candidates = []
        for parent, directories, filenames in os.walk(directory, followlinks=False):
            base = Path(parent)
            directories[:] = [name for name in directories if _contido(root, base / name)]
            candidates.extend(base / name for name in filenames
                              if any(Path(name).match(pattern) for pattern in patterns))
        for path in candidates:
            if not _contido(root, path):
                rejected += 1
                continue
            if path.is_file() and path.stat().st_mtime < cutoff:
                counts[category] += 1
                if confirmar:
                    path.unlink()
    return {'aplicado': bool(confirmar), 'contagens': counts, 'recusados': rejected,
            'fatos_salvos': 'mantidos ate esquecimento explicito',
            'limites': 'Nao apaga backups, OneDrive ou outras copias; nao e apagamento seguro do disco.'}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raiz', required=True, help='Pasta do projeto, com o Auren encerrado')
    parser.add_argument('--aplicar', action='store_true', help='Confirma a exclusão dos registros vencidos')
    args = parser.parse_args()
    print(json.dumps(aplicar_retencao(args.raiz, confirmar=args.aplicar), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
