"""Build the structured-facts summary shown in the Summary and Raw context tabs."""
from __future__ import annotations

from collections import Counter

from .github import FetchResult
from .manifests import Manifest

_EXT_TO_LANG = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".kt": "Kotlin",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".cs": "C#",
    ".cpp": "C++",
    ".c": "C",
    ".swift": "Swift",
    ".m": "Objective-C",
    ".scala": "Scala",
    ".php": "PHP",
    ".sh": "Shell",
}


def language_breakdown(tree):
    counts = Counter()
    for e in tree:
        if e.get("type") != "blob":
            continue
        path = e.get("path", "")
        idx = path.rfind(".")
        if idx == -1:
            continue
        lang = _EXT_TO_LANG.get(path[idx:].lower())
        if lang:
            counts[lang] += 1
    return counts.most_common()


def top_level_layout(tree, limit=25):
    seen = set()
    out = []
    for e in tree:
        path = e.get("path", "")
        if "/" in path:
            first = path.split("/", 1)[0]
            if first in seen:
                continue
            seen.add(first)
            out.append(f"DIR  {first}")
        else:
            if path in seen:
                continue
            seen.add(path)
            kind = "DIR " if e.get("type") == "tree" else "FILE"
            out.append(f"{kind} {path}")
    out.sort()
    return out[:limit]


def _readme_excerpt(files, max_chars=6000):
    for name in ("README.md", "README.rst", "README.txt", "README"):
        text = files.get(name)
        if text:
            return text[:max_chars]
    return ""


def build_context(fetched, manifests, edge_summary):
    parts = [
        "# Repository quick facts",
        f"Repo: {fetched.owner}/{fetched.repo}  (branch: {fetched.branch})",
    ]
    if fetched.truncated:
        parts.append("Note: GitHub truncated the file tree (very large repo).")
    if fetched.skipped_source_files:
        parts.append(
            f"Note: capped to first {len(fetched.files)} fetched files; "
            f"{fetched.skipped_source_files} additional source files were not parsed."
        )
    langs = language_breakdown(fetched.tree)
    if langs:
        parts.append("\n## Languages (by file count across the full tree)")
        parts.extend(f"- {lang}: {n}" for lang, n in langs[:8])
    parts.append("\n## Top-level layout")
    parts.extend(top_level_layout(fetched.tree))
    if manifests:
        parts.append("\n## Dependency manifests")
        for m in manifests:
            head = ", ".join((m.deps or [])[:8]) or "(none)"
            parts.append(f"- {m.file} [{m.ecosystem}]: {len(m.deps)} deps - e.g. {head}")
    parts.append("\n## Internal import signal")
    any_edges = False
    for lang, summary in edge_summary.items():
        if summary["edge_count"] == 0:
            continue
        any_edges = True
        parts.append(
            f"- {lang}: {summary['node_count']} modules, {summary['edge_count']} edges"
        )
        top = summary["top_imported"][:5]
        if top:
            parts.append("  most imported: " + ", ".join(f"{m} ({c})" for m, c in top))
    if not any_edges:
        parts.append("- (no internal edges detected in parsed languages)")
    readme = _readme_excerpt(fetched.files)
    if readme:
        parts.append("\n## README excerpt")
        parts.append(readme)
    return "\n".join(parts)
