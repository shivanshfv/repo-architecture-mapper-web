"""Fetch a GitHub repo's interesting files via the REST API + raw URLs.

In-memory, no subprocess, no filesystem writes. Returns a dict of
{path: content} plus the original tree entries.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/(?P<owner>[A-Za-z0-9._-]+)/"
    r"(?P<repo>[A-Za-z0-9._-]+?)(?:\.git)?/?$"
)

MANIFEST_NAMES = {
    "requirements.txt",
    "requirements-dev.txt",
    "pyproject.toml",
    "package.json",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "go.mod",
    "Cargo.toml",
    "Gemfile",
}
SOURCE_EXTS = (".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".java", ".kt")
README_NAMES = {"README.md", "README.rst", "README.txt", "README"}
HINT_FILES = {
    ".env.example",
    ".env.sample",
    ".env.template",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Makefile",
}
SKIP_DIR_PARTS = {"node_modules", "vendor", "dist", "build", "target", ".git", "__pycache__"}


@dataclass
class FetchResult:
    owner: str
    repo: str
    branch: str
    files: dict[str, str] = field(default_factory=dict)
    tree: list[dict] = field(default_factory=list)
    truncated: bool = False
    skipped_source_files: int = 0


def parse_repo_url(url: str) -> tuple[str, str]:
    m = _URL_RE.match(url.strip())
    if not m:
        raise ValueError(
            f"Not a recognized GitHub URL: {url!r}. "
            "Use https://github.com/<owner>/<repo>"
        )
    return m.group("owner"), m.group("repo")


def _headers(token, accept_json):
    h = {"User-Agent": "repo-architecture-mapper"}
    if accept_json:
        h["Accept"] = "application/vnd.github+json"
    if token:
        h["Authorization"] = f"token {token}"
    return h


def _api_json(url, token, timeout=15):
    req = urllib.request.Request(url, headers=_headers(token, accept_json=True))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _raw_text(owner, repo, branch, path, token, timeout=10):
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
    req = urllib.request.Request(url, headers=_headers(token, accept_json=False))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


def _default_branch(owner, repo, token):
    info = _api_json(f"https://api.github.com/repos/{owner}/{repo}", token=token)
    return info.get("default_branch") or "main"


def _classify_paths(entries, max_source_files):
    manifest_paths, readme_paths, hint_paths, source_paths = [], [], [], []
    for e in entries:
        if e.get("type") != "blob":
            continue
        path = e["path"]
        parts = path.split("/")
        if any(p in SKIP_DIR_PARTS for p in parts):
            continue
        name = parts[-1]
        size = e.get("size") or 0
        if name in MANIFEST_NAMES:
            manifest_paths.append(path)
        elif name in README_NAMES and "/" not in path:
            readme_paths.append(path)
        elif name in HINT_FILES and "/" not in path:
            hint_paths.append(path)
        elif name.endswith(SOURCE_EXTS) and size <= 500_000:
            source_paths.append(path)
    skipped = max(0, len(source_paths) - max_source_files)
    return manifest_paths, readme_paths, hint_paths, source_paths[:max_source_files], skipped


def fetch_repo(url, *, token=None, max_source_files=60):
    owner, repo = parse_repo_url(url)
    branch = _default_branch(owner, repo, token)
    tree_data = _api_json(
        f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1",
        token=token,
    )
    entries = tree_data.get("tree", []) or []
    truncated = bool(tree_data.get("truncated"))
    manifests, readmes, hints, sources, skipped = _classify_paths(entries, max_source_files)
    targets = manifests + readmes + hints + sources

    files = {}
    if targets:
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = {
                pool.submit(_raw_text, owner, repo, branch, p, token): p
                for p in targets
            }
            for fut in as_completed(futures):
                path = futures[fut]
                try:
                    files[path] = fut.result()
                except (urllib.error.URLError, TimeoutError):
                    continue
                except Exception:  # noqa: BLE001
                    continue

    return FetchResult(
        owner=owner, repo=repo, branch=branch,
        files=files, tree=entries,
        truncated=truncated, skipped_source_files=skipped,
    )
