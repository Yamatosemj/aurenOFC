import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.router import Router
from core.tools_registry import tools
from medir_router_baseline import CASES


def test_baseline_matrix_is_deterministic():
    router = Router()
    all_names = [item["name"] for item in tools]

    for text, _fast_path in CASES:
        first = router.select_tool_names(text, tools)
        first_domains = list(router.last_domains)
        second = router.select_tool_names(text, tools)
        second_domains = list(router.last_domains)

        assert first == second, text
        assert first_domains == second_domains, text
        assert 1 <= len(first) <= len(all_names), text


def test_baseline_documents_memory_gap():
    router = Router()
    names = router.select_tool_names(
        "salve na memória que minha playlist de trabalho é X",
        tools,
    )
    assert names == [item["name"] for item in tools]
    assert router.last_domains == []
