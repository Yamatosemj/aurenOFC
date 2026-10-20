"""Lossless, opt-in JSON formatting experiments; no context selection."""
import json
import os


def context_json(value, *, component):
    flag = {"reviews": "AUREN_CONTEXT_COMPACT_REVIEWS",
            "plan": "AUREN_CONTEXT_COMPACT_PLAN"}[component]
    kwargs = {"ensure_ascii": False}
    if os.getenv(flag) == "1":
        kwargs["separators"] = (",", ":")
    return json.dumps(value, **kwargs)
