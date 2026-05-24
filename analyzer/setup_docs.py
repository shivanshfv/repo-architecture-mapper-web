"""Generate setup docs from manifests, scripts, and README hints."""
from __future__ import annotations

import re

from .manifests import Manifest


def _extract_readme_setup(files):
    for name in ("README.md", "README.rst", "README.txt", "README"):
        text = files.get(name)
        if not text:
            continue
        sections = re.split(r"\n(?=#{1,3}\s)", text)
        wanted = []
        for sec in sections:
            header = sec.splitlines()[0].lower() if sec else ""
            if any(
                k in header
                for k in ("install", "setup", "getting started", "quick start", "usage", "run")
            ):
                wanted.append(sec.strip())
        if wanted:
            return "\n\n".join(wanted[:4])[:4000]
    return ""


def _inferred_commands(manifests):
    cmds = []
    ecosystems = {m.ecosystem for m in manifests}
    names = {m.file.rsplit("/", 1)[-1] for m in manifests}
    if "python" in ecosystems:
        if "pyproject.toml" in names:
            cmds.append(("Install Python deps", "pip install ."))
        if any(n.startswith("requirements") for n in names):
            cmds.append(("Install Python deps", "pip install -r requirements.txt"))
    if "javascript" in ecosystems:
        cmds.append(("Install Node deps", "npm install   # or: yarn / pnpm install"))
        for m in manifests:
            if m.ecosystem == "javascript" and m.scripts:
                for name in ("dev", "start", "build", "test"):
                    if name in m.scripts:
                        cmds.append((f"npm script: {name}", f"npm run {name}"))
                break
    if "java" in ecosystems:
        if "pom.xml" in names:
            cmds.append(("Build (Maven)", "mvn clean install"))
        if any(n.startswith("build.gradle") for n in names):
            cmds.append(("Build (Gradle)", "./gradlew build"))
    if "go" in ecosystems:
        cmds.append(("Fetch Go modules", "go mod download"))
        cmds.append(("Build", "go build ./..."))
    if "rust" in ecosystems:
        cmds.append(("Build (Cargo)", "cargo build"))
        cmds.append(("Test", "cargo test"))
    if "ruby" in ecosystems:
        cmds.append(("Install gems", "bundle install"))
    return cmds


def _env_hints(files):
    hints = []
    for candidate in (".env.example", ".env.sample", ".env.template"):
        if candidate in files:
            hints.append(f"Copy `{candidate}` -> `.env` and fill in required values.")
            break
    if "docker-compose.yml" in files or "docker-compose.yaml" in files:
        hints.append("Docker Compose detected -> `docker compose up` brings dependencies up locally.")
    if "Dockerfile" in files:
        hints.append("Dockerfile detected -> image can be built with `docker build -t <name> .`")
    if "Makefile" in files:
        hints.append("Makefile present -> run `make help` (or open it) to see available targets.")
    return hints


def build_setup_docs(repo_name, files, manifests):
    out = ["# Setup", ""]
    out.append("## 1. Clone")
    out.append(f"```bash\ngit clone <repo-url>\ncd {repo_name}\n```")
    cmds = _inferred_commands(manifests)
    if cmds:
        out.append("\n## 2. Inferred setup commands")
        for label, cmd in cmds:
            out.append(f"- **{label}**")
            out.append(f"  ```bash\n  {cmd}\n  ```")
    env = _env_hints(files)
    if env:
        out.append("\n## 3. Environment / runtime hints")
        for h in env:
            out.append(f"- {h}")
    readme_section = _extract_readme_setup(files)
    if readme_section:
        out.append("\n## 4. Setup notes from the README")
        out.append(readme_section)
    out.append(
        "\n---\n_These steps are inferred from manifests and README headings. "
        "Verify against the project's own docs before running in a clean environment._"
    )
    return "\n".join(out)
