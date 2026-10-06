from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.router import Router
from core.tools_registry import tools

# Matriz fixa do baseline. Ela descreve pedidos representativos sem executar
# nenhuma ferramenta e sem chamar a API. A coluna fast_path e uma anotacao
# documental baseada nos caminhos determinísticos já existentes em fast_paths.py.
CASES = [
    ("que horas são?", True),
    ("que dia é hoje?", True),
    ("volume 40%", False),
    ("abra o YouTube", True),
    ("pesquise Create Aeronautics no YouTube", False),
    ("maximize a janela do Notepad", False),
    ("leia a área de transferência", False),
    ("clique no mouse em x=500 y=300", False),
    ("liste os processos do Windows", False),
    ("qual o uso da memória RAM?", False),
    ("abra o Discord", True),
    ("procure o arquivo meu documento pdf", False),
    ("salve na memória que minha playlist de trabalho é X", False),
    ("o que você acha disso?", False),
    ("abra o Chrome", False),
    ("mova a janela do Bloco de Notas para 100,100", False),
    ("inspecione a interface da janela AUREN_UIA_TESTE procurando Campo de Teste", False),
    ("marque a caixa Check Auren Teste da janela AUREN_UIA_TESTE_X", False),
    ("qual é o estado do Windows?", False),
    ("lembre que minha playlist de trabalho é X", False),
]


def collect() -> list[dict]:
    router = Router()
    all_names = [item["name"] for item in tools]
    rows: list[dict] = []

    for text, fast_path in CASES:
        names = router.select_tool_names(text, tools)
        domains = list(router.last_domains)
        rows.append(
            {
                "pedido": text,
                "fast_path": fast_path,
                "dominios": domains,
                "ferramentas": len(names),
                "fallback_44": len(names) == len(all_names),
                "ferramentas_selecionadas": names,
            }
        )
    return rows


def markdown(rows: list[dict]) -> str:
    lines = [
        "# B1 — Mapa comportamental do Router V43 Ouro Limpo",
        "",
        "Medição local e determinística. Nenhuma API ou ferramenta real é executada.",
        "",
        "| Pedido | Fast Path | Domínio | Ferramentas | Fallback 44 |",
        "|---|---:|---|---:|---:|",
    ]
    for row in rows:
        domain = ", ".join(row["dominios"]) if row["dominios"] else "nenhum"
        lines.append(
            f"| `{row['pedido']}` | {'sim' if row['fast_path'] else 'não'} | {domain} | {row['ferramentas']} | {'sim' if row['fallback_44'] else 'não'} |"
        )

    total = len(rows)
    fallback = sum(r["fallback_44"] for r in rows)
    fast = sum(r["fast_path"] for r in rows)
    specialized = total - fallback
    sizes = [r["ferramentas"] for r in rows]

    lines += [
        "",
        "## Resumo da amostra",
        "",
        f"- pedidos: {total}",
        f"- Fast Path anotado: {fast}",
        f"- fallback para 44 ferramentas: {fallback}",
        f"- rotas menores que 44: {specialized}",
        f"- menor toolset: {min(sizes)}",
        f"- maior toolset: {max(sizes)}",
        f"- média de ferramentas: {sum(sizes) / total:.2f}",
        "",
        "## Achados da matriz",
        "",
        "- Perguntas de hora/data podem ser concluídas pelo Fast Path, embora o Router isolado não detecte domínio e retornaria 44 ferramentas.",
        "- O domínio `memory` ainda não captura `salve na memória ...` nesta formulação específica; o Router cai no fallback de 44.",
        "- `lembre que ...` também permanece no fallback nesta matriz.",
        "- Browser, Windows, UIA, áudio, clipboard, input, process, system e apps_files possuem rotas especializadas observáveis.",
        "",
        "Nenhuma dessas lacunas é corrigida no B1. Elas são baseline para o B2/experimento posterior.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    rows = collect()
    output = {
        "versao": 43,
        "total_casos": len(rows),
        "casos": rows,
    }

    out_dir = ROOT / "logs" / "testes"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "BASELINE_ROUTER_V43_OURO_LIMPO.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "RELATORIO_BASELINE_ROUTER_V43_OURO_LIMPO.md").write_text(
        markdown(rows),
        encoding="utf-8",
    )

    print(markdown(rows))
    print(f"JSON salvo em: {out_dir / 'BASELINE_ROUTER_V43_OURO_LIMPO.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
