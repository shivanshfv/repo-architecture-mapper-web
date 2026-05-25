"""Single entrypoint for the deployed app.

Vercel's Python runtime routes every request through this handler, so it
serves both the static frontend (GET /, /app.js, /styles.css) and the
analysis endpoint (POST /api/analyze).

POST /api/analyze body:
  {
    "url": "https://github.com/owner/repo",
    "github_token": "<optional>",
    "depth": 2,
    "max_source_files": 60
  }
"""
from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analyzer.context import build_context, language_breakdown, top_level_layout
from analyzer.github import fetch_repo
from analyzer.graph import build_graph_json
from analyzer.imports import collect_edges, edge_summary
from analyzer.manifests import discover_manifests
from analyzer.setup_docs import build_setup_docs

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STATIC_ROUTES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/app.js": "app.js",
    "/styles.css": "styles.css",
}

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
}


def _serialize_manifest(m):
    return {
        "ecosystem": m.ecosystem,
        "file": m.file,
        "deps": m.deps,
        "dev_deps": m.dev_deps,
        "scripts": m.scripts,
    }


def _serialize_summary(summary):
    return {
        lang: {
            "edge_count": s["edge_count"],
            "node_count": s["node_count"],
            "top_imported": [{"name": n, "count": c} for n, c in s["top_imported"]],
            "top_importers": [{"name": n, "count": c} for n, c in s["top_importers"]],
        }
        for lang, s in summary.items()
    }


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        path = urlparse(self.path).path
        target = STATIC_ROUTES.get(path)
        if target is None:
            return self._not_found()
        file_path = os.path.join(PROJECT_ROOT, target)
        try:
            with open(file_path, "rb") as f:
                body = f.read()
        except FileNotFoundError:
            return self._not_found()
        ext = os.path.splitext(target)[1]
        ctype = CONTENT_TYPES.get(ext, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/api/analyze":
            return self._not_found()
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
        except json.JSONDecodeError:
            return self._json({"error": "invalid JSON body"}, 400)

        url = (body.get("url") or "").strip()
        if not url:
            return self._json({"error": "missing 'url'"}, 400)
        token = (body.get("github_token") or "").strip() or None
        try:
            depth = int(body.get("depth", 2))
            max_files = int(body.get("max_source_files", 60))
        except (TypeError, ValueError):
            return self._json({"error": "depth and max_source_files must be integers"}, 400)

        try:
            fetched = fetch_repo(url, token=token, max_source_files=max_files)
        except ValueError as e:
            return self._json({"error": str(e)}, 400)
        except Exception as e:  # noqa: BLE001
            return self._json({"error": f"GitHub fetch failed: {type(e).__name__}: {e}"}, 502)

        manifests = discover_manifests(fetched.files)
        edges = collect_edges(fetched.files)
        summary = edge_summary(edges)
        graphs = {lang: build_graph_json(e, depth=depth) for lang, e in edges.items() if e}
        setup_md = build_setup_docs(fetched.repo, fetched.files, manifests)
        context = build_context(fetched, manifests, summary)

        self._json({
            "owner": fetched.owner,
            "repo": fetched.repo,
            "branch": fetched.branch,
            "truncated": fetched.truncated,
            "skipped_source_files": fetched.skipped_source_files,
            "fetched_file_count": len(fetched.files),
            "manifests": [_serialize_manifest(m) for m in manifests],
            "edge_summary": _serialize_summary(summary),
            "graphs": graphs,
            "setup_md": setup_md,
            "context": context,
            "languages": language_breakdown(fetched.tree),
            "layout": top_level_layout(fetched.tree),
        })

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _not_found(self):
        msg = b"Not found"
        self.send_response(404)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(msg)))
        self.end_headers()
        self.wfile.write(msg)

    def log_message(self, format, *args):  # noqa: A002
        return
