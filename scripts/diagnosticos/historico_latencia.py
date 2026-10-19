"""Read existing traces in SQLite read-only mode; export aggregates only."""
import argparse
import json
from pathlib import Path
import sqlite3
from statistics import median
from core.task_trace import _percentile

def summarize(values):
    return {"n": len(values), "median_ms": round(median(values), 3) if values else None,
            "p95_ms": round(_percentile(values, 95), 3) if len(values) >= 20 else None}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with sqlite3.connect(args.database.resolve().as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute('SELECT * FROM task_traces WHERE finished_at IS NOT NULL').fetchall()
        spans = db.execute('SELECT category,name,duration_ms FROM task_trace_spans').fetchall()
    result = {'source': 'historical_mixed_versions_unknown_test_provenance', 'tasks': len(rows),
              'warning': 'model spans include application overhead; not isolated API latency',
              'stages': {}, 'by_type': {}}
    for category in sorted({r['category'] for r in spans}):
        result['stages'][category] = summarize([r['duration_ms'] for r in spans if r['category'] == category])
    for kind in sorted({r['task_type'] for r in rows}):
        group = [r for r in rows if r['task_type'] == kind]
        result['by_type'][kind] = {key: summarize([r[key] for r in group])
                                  for key in ('total_ms', 'context_ms', 'model_ms', 'tool_ms')}
        result['by_type'][kind]['model_calls'] = sum(r['model_rounds'] for r in group)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
