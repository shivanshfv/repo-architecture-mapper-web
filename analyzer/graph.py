"""Build a JSON-serializable graph (nodes + weighted edges) for the
frontend to render."""
from __future__ import annotations

from collections import defaultdict

from .imports import ModuleEdge


def _collapse(name, depth):
    if not name:
        return name
    if "." in name and "/" not in name:
        parts = name.split(".")
    else:
        parts = name.replace("\\", "/").split("/")
    return ".".join(parts[:depth]) if parts else name


def build_graph_json(edges, *, depth=2):
    weighted = defaultdict(int)
    for e in edges:
        a = _collapse(e.src, depth)
        b = _collapse(e.dst, depth)
        if not a or not b or a == b:
            continue
        weighted[(a, b)] += 1
    nodes = sorted({n for pair in weighted for n in pair})
    edges_out = [
        {"from": a, "to": b, "weight": w}
        for (a, b), w in sorted(weighted.items())
    ]
    return {"nodes": nodes, "edges": edges_out}
