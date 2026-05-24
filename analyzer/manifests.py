"""Parse dependency manifests across common ecosystems. Operates on
in-memory file contents (path -> text)."""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field


@dataclass
class Manifest:
    ecosystem: str
    file: str
    deps: list[str] = field(default_factory=list)
    dev_deps: list[str] = field(default_factory=list)
    scripts: dict[str, str] = field(default_factory=dict)


def _parse_requirements(path, text):
    deps = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        name = re.split(r"[<>=!~ ;]", line, 1)[0].strip()
        if name:
            deps.append(name)
    return Manifest(ecosystem="python", file=path, deps=deps)


def _parse_pyproject(path, text):
    try:
        import tomllib
    except ModuleNotFoundError:
        try:
            import tomli as tomllib  # type: ignore
        except ModuleNotFoundError:
            return Manifest(ecosystem="python", file=path)
    try:
        data = tomllib.loads(text)
    except Exception:  # noqa: BLE001
        return Manifest(ecosystem="python", file=path)
    deps = []
    project = data.get("project") or {}
    for d in project.get("dependencies", []) or []:
        deps.append(re.split(r"[<>=!~ ;\[]", d, 1)[0].strip())
    poetry = (data.get("tool") or {}).get("poetry") or {}
    for k in poetry.get("dependencies") or {}:
        if k.lower() != "python":
            deps.append(k)
    return Manifest(ecosystem="python", file=path, deps=[d for d in deps if d])


def _parse_package_json(path, text):
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return Manifest(ecosystem="javascript", file=path)
    return Manifest(
        ecosystem="javascript",
        file=path,
        deps=list((data.get("dependencies") or {}).keys()),
        dev_deps=list((data.get("devDependencies") or {}).keys()),
        scripts={k: str(v) for k, v in (data.get("scripts") or {}).items()},
    )


def _parse_pom(path, text):
    deps = []
    try:
        cleaned = re.sub(r'\sxmlns="[^"]+"', "", text, count=1)
        root = ET.fromstring(cleaned)
        for dep in root.iterfind(".//dependency"):
            group = (dep.findtext("groupId") or "").strip()
            artifact = (dep.findtext("artifactId") or "").strip()
            if group or artifact:
                deps.append(f"{group}:{artifact}".strip(":"))
    except ET.ParseError:
        pass
    return Manifest(ecosystem="java", file=path, deps=deps)


_GRADLE_DEP_RE = re.compile(
    r"""(?:implementation|api|compile|runtimeOnly|testImplementation|kapt|ksp)\s*"""
    r"""[\(\s]\s*['"]([^'"]+)['"]""",
    re.MULTILINE,
)


def _parse_gradle(path, text):
    deps = sorted({m.group(1) for m in _GRADLE_DEP_RE.finditer(text)})
    return Manifest(ecosystem="java", file=path, deps=deps)


def _parse_go_mod(path, text):
    deps = []
    in_block = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("require ("):
            in_block = True
            continue
        if in_block:
            if s == ")":
                in_block = False
                continue
            parts = s.split()
            if parts:
                deps.append(parts[0])
        elif s.startswith("require "):
            parts = s.split()
            if len(parts) >= 2:
                deps.append(parts[1])
    return Manifest(ecosystem="go", file=path, deps=deps)


def _parse_cargo(path, text):
    try:
        import tomllib
    except ModuleNotFoundError:
        try:
            import tomli as tomllib  # type: ignore
        except ModuleNotFoundError:
            return Manifest(ecosystem="rust", file=path)
    try:
        data = tomllib.loads(text)
    except Exception:  # noqa: BLE001
        return Manifest(ecosystem="rust", file=path)
    return Manifest(
        ecosystem="rust",
        file=path,
        deps=list((data.get("dependencies") or {}).keys()),
        dev_deps=list((data.get("dev-dependencies") or {}).keys()),
    )


_GEM_RE = re.compile(r"^\s*gem\s+['\"]([^'\"]+)['\"]")


def _parse_gemfile(path, text):
    return Manifest(
        ecosystem="ruby", file=path,
        deps=[m.group(1) for m in _GEM_RE.finditer(text)],
    )


_PARSERS = {
    "requirements.txt": _parse_requirements,
    "requirements-dev.txt": _parse_requirements,
    "pyproject.toml": _parse_pyproject,
    "package.json": _parse_package_json,
    "pom.xml": _parse_pom,
    "build.gradle": _parse_gradle,
    "build.gradle.kts": _parse_gradle,
    "go.mod": _parse_go_mod,
    "Cargo.toml": _parse_cargo,
    "Gemfile": _parse_gemfile,
}


def discover_manifests(files):
    found = []
    for path, content in files.items():
        name = path.rsplit("/", 1)[-1]
        parser = _PARSERS.get(name)
        if not parser:
            continue
        try:
            found.append(parser(path, content))
        except Exception:  # noqa: BLE001
            continue
    found.sort(key=lambda m: m.file)
    return found
