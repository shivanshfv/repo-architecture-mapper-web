"""Parse internal module imports from in-memory file contents."""
from __future__ import annotations

import ast
import posixpath
import re
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class ModuleEdge:
    src: str
    dst: str


# Python -------------------------------------------------------------------

def _python_module(path):
    parts = path.replace("\\", "/").split("/")
    if parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _python_edges(files):
    py = {p: c for p, c in files.items() if p.endswith(".py")}
    internal = {_python_module(p) for p in py}
    roots = {m.split(".", 1)[0] for m in internal if m}
    edges = []
    for path, content in py.items():
        src = _python_module(path)
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".", 1)[0] in roots:
                        edges.append(ModuleEdge(src=src, dst=alias.name))
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    parts = src.split(".")
                    base = parts[: max(0, len(parts) - node.level)]
                    target = ".".join([*base, node.module]) if node.module else ".".join(base)
                    if target:
                        edges.append(ModuleEdge(src=src, dst=target))
                elif node.module and node.module.split(".", 1)[0] in roots:
                    edges.append(ModuleEdge(src=src, dst=node.module))
    return edges


# JS / TS ------------------------------------------------------------------

_JS_EXTS = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")
_JS_IMPORT_RE = re.compile(
    r"""(?:import\s[^'"]*?from\s*|import\s*|require\s*\(\s*)['"]([^'"]+)['"]""",
    re.MULTILINE,
)


def _js_module(path):
    for ext in _JS_EXTS:
        if path.endswith(ext):
            return path[: -len(ext)]
    return path


def _resolve_relative(src_path, spec):
    src_dir = posixpath.dirname(src_path)
    resolved = posixpath.normpath(posixpath.join(src_dir, spec))
    if resolved.startswith("../") or resolved.startswith("/"):
        return None
    return resolved


def _js_edges(files):
    edges = []
    for path, content in files.items():
        if not path.endswith(_JS_EXTS):
            continue
        src = _js_module(path)
        for m in _JS_IMPORT_RE.finditer(content):
            spec = m.group(1)
            if spec.startswith("."):
                resolved = _resolve_relative(path, spec)
                if resolved is not None:
                    edges.append(ModuleEdge(src=src, dst=resolved))
    return edges


# Java / Kotlin ------------------------------------------------------------

_JAVA_PACKAGE_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;?", re.MULTILINE)
_JAVA_IMPORT_RE = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)\s*;", re.MULTILINE)


def _java_edges(files):
    internal_packages = set()
    file_to_pkg = {}
    java = {p: c for p, c in files.items() if p.endswith((".java", ".kt"))}
    for path, content in java.items():
        m = _JAVA_PACKAGE_RE.search(content)
        if m:
            internal_packages.add(m.group(1))
            file_to_pkg[path] = m.group(1)
    roots = {p.split(".", 1)[0] for p in internal_packages}
    edges = []
    for path, src_pkg in file_to_pkg.items():
        for m in _JAVA_IMPORT_RE.finditer(java[path]):
            target = m.group(1)
            if target.split(".", 1)[0] in roots:
                target_pkg = target.rsplit(".", 1)[0]
                if target_pkg != src_pkg:
                    edges.append(ModuleEdge(src=src_pkg, dst=target_pkg))
    return edges


def collect_edges(files):
    return {
        "python": _python_edges(files),
        "javascript": _js_edges(files),
        "java": _java_edges(files),
    }


def edge_summary(edges_by_lang):
    out = {}
    for lang, edges in edges_by_lang.items():
        outgoing = defaultdict(int)
        incoming = defaultdict(int)
        for e in edges:
            outgoing[e.src] += 1
            incoming[e.dst] += 1
        out[lang] = {
            "edge_count": len(edges),
            "node_count": len(set(outgoing) | set(incoming)),
            "top_imported": sorted(incoming.items(), key=lambda x: -x[1])[:10],
            "top_importers": sorted(outgoing.items(), key=lambda x: -x[1])[:10],
        }
    return out
