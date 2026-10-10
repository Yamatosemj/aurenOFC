"""Mede rodadas e tokens por TASK em um chat.log do Auren.

Uso:
    py scripts/diagnosticos/medir_custo_modelo.py
    py medir_custo_modelo.py logs/chats/<chat_id>/chat/chat.log

Este utilitario nao chama OpenAI. Ele serve para decidir quais cenarios
precisam continuar em L4/L5 e onde o historico da conversa esta crescendo.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

TS = r"\[\d{4}-\d{2}-\d{2}T[^\]\n]+\]"
TASK_RE = re.compile(rf"(?ms)^{TS} TASK_START\n.*?(?=^{TS} TASK_START\n|^{TS} CHAT_END\n|\Z)")
ROUND_RE = re.compile(rf"(?m)^{TS} MODEL_ROUND_REQUEST\b")
TOOL_RE = re.compile(r'(?m)^  ferramenta: "([^"]+)"')
TOKEN_RE = re.compile(
    r'"?(input_tokens|output_tokens|cached_tokens|cache_write_tokens)"?\s*[:=]\s*(\d+)'
)


def find_log(argv: list[str]) -> Path:
    if len(argv) > 1:
        return Path(argv[1])
    logs = sorted((Path(__file__).resolve().parents[2] / "logs/chats").glob("*/chat/chat.log"), key=lambda p: p.stat().st_mtime)
    if not logs:
        raise SystemExit("Nenhum chat.log encontrado em logs/chats.")
    return logs[-1]


def label(block: str) -> str:
    for line in block.splitlines()[1:8]:
        if line.strip().startswith('objetivo:'):
            return line.strip()[:100]
    return "?"


def main() -> None:
    path = find_log(sys.argv)
    text = path.read_text(encoding="utf-8", errors="replace")
    blocks = TASK_RE.findall(text)
    rows = []
    for block in blocks:
        tokens = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0, "cache_write_tokens": 0}
        for kind, value in TOKEN_RE.findall(block):
            tokens[kind] += int(value)
        rows.append(
            (
                len(ROUND_RE.findall(block)),
                tokens["input_tokens"],
                tokens["output_tokens"],
                tokens["cached_tokens"],
                tokens["cache_write_tokens"],
                "TASK_FAST_PATH" in block,
                label(block),
                sorted(set(TOOL_RE.findall(block))),
            )
        )

    print(f"Log: {path}")
    print(f"Tarefas: {len(rows)}\n")
    print(f"{'rod':>3} {'in_tok':>9} {'out_tok':>9} {'cache':>9} {'write':>9} fast  tarefa / ferramentas")
    for rounds, in_tok, out_tok, cached, cache_write, fast, task_label, tools in sorted(rows, key=lambda x: (-x[0], -x[1])):
        print(
            f"{rounds:>3} {in_tok:>9} {out_tok:>9} {cached:>9} {cache_write:>9} {'sim' if fast else 'nao '}  "
            f"{task_label}  [{', '.join(tools)}]"
        )

    total_rounds = sum(row[0] for row in rows)
    total_in = sum(row[1] for row in rows)
    total_out = sum(row[2] for row in rows)
    total_cached = sum(row[3] for row in rows)
    total_cache_write = sum(row[4] for row in rows)
    fast_count = sum(1 for row in rows if row[5])
    print(
        f"\nTotal de rodadas: {total_rounds} | input_tokens: {total_in} | "
        f"output_tokens: {total_out} | cached_tokens: {total_cached} | "
        f"cache_write_tokens: {total_cache_write} | fast_path: {fast_count}"
    )
    if rows:
        model_rows = [row for row in rows if row[0] > 0]
        if model_rows:
            print(f"Media por tarefa com modelo: {total_rounds / len(model_rows):.2f} rodada(s)")
            print(f"Media de input por tarefa com modelo: {total_in / len(model_rows):.0f} tokens")


if __name__ == "__main__":
    main()
