#!/usr/bin/env python3
"""Static release gate for OrbisERP.

Runs without importing Flask or connecting to PostgreSQL. It catches broken Python,
Jinja syntax, missing static assets, invalid url_for endpoints, Alembic graph splits,
legacy duplicate templates and JavaScript syntax errors before dynamic QA starts.
"""
from __future__ import annotations

import ast
import compileall
import re
import shutil
import subprocess
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, TemplateSyntaxError

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"
MIGRATIONS = ROOT / "migrations" / "versions"

LEGACY_TEMPLATES = {
    "templates/sales/pending.html",
    "templates/sales/quotes.html",
    "templates/sales/sales.html",
    "templates/workspace/activity.html",
    "templates/workspace/executive.html",
    "templates/cash/close.html",
}

URL_FOR_RE = re.compile(r"url_for\(\s*['\"]([^'\"]+)['\"]")
STATIC_URL_RE = re.compile(
    r"url_for\(\s*['\"]static['\"]\s*,\s*filename\s*=\s*['\"]([^'\"]+)['\"]"
)
HARD_STATIC_RE = re.compile(r"(?:href|src)\s*=\s*['\"](/static/[^'\"?#]+)", re.I)


def _python_files():
    excluded = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache"}
    for path in ROOT.rglob("*.py"):
        if not any(part in excluded for part in path.relative_to(ROOT).parts):
            yield path


def _source_files():
    for pattern in ("*.py", "*.html"):
        for path in ROOT.rglob(pattern):
            rel = path.relative_to(ROOT)
            if not any(part in {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache"} for part in rel.parts):
                yield path


def _collect_endpoints():
    endpoints = {"static"}
    parsed: list[tuple[Path, ast.AST]] = []
    blueprints: dict[str, str] = {}
    # First pass: blueprint objects can be declared in one module and imported
    # by sibling modules (the sales package follows this pattern).
    for path in _python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        parsed.append((path, tree))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                call = node.value
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "Blueprint" and call.args:
                    name = call.args[0]
                    if isinstance(name, ast.Constant) and isinstance(name.value, str):
                        blueprints[node.targets[0].id] = name.value
    for path, tree in parsed:
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                    continue
                owner = decorator.func.value
                method = decorator.func.attr
                if method not in {"route", "get", "post", "put", "delete", "patch"} or not isinstance(owner, ast.Name):
                    continue
                endpoint_name = node.name
                for keyword in decorator.keywords:
                    if keyword.arg == "endpoint" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                        endpoint_name = keyword.value.value
                if owner.id in blueprints:
                    endpoints.add(f"{blueprints[owner.id]}.{endpoint_name}")
                elif owner.id == "app":
                    endpoints.add(endpoint_name)
    return endpoints


def check_python(errors: list[str]):
    if not compileall.compile_dir(str(ROOT), quiet=1, force=True):
        errors.append("Python compileall failed")


def check_jinja(errors: list[str]):
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    count = 0
    for path in sorted(TEMPLATES.rglob("*.html")):
        name = path.relative_to(TEMPLATES).as_posix()
        try:
            env.get_template(name)
            count += 1
        except TemplateSyntaxError as exc:
            errors.append(f"Jinja {name}:{exc.lineno}: {exc.message}")
    return count


def check_assets_and_endpoints(errors: list[str]):
    endpoints = _collect_endpoints()
    endpoint_refs = 0
    asset_refs = 0
    for path in _source_files():
        source = path.read_text(encoding="utf-8", errors="replace")
        for match in URL_FOR_RE.finditer(source):
            endpoint = match.group(1)
            endpoint_refs += 1
            if endpoint not in endpoints:
                errors.append(f"Unknown url_for endpoint {endpoint!r} in {path.relative_to(ROOT)}")
        for match in STATIC_URL_RE.finditer(source):
            asset_refs += 1
            asset = STATIC / match.group(1)
            if not asset.is_file():
                errors.append(f"Missing static asset {match.group(1)!r} in {path.relative_to(ROOT)}")
        for match in HARD_STATIC_RE.finditer(source):
            asset_refs += 1
            rel = match.group(1).removeprefix("/static/")
            if "{{" in rel or "{%" in rel:
                continue
            asset = STATIC / rel
            if not asset.is_file():
                errors.append(f"Missing hard-coded static asset {rel!r} in {path.relative_to(ROOT)}")
    return len(endpoints), endpoint_refs, asset_refs


def check_migrations(errors: list[str]):
    revisions: dict[str, tuple[str | None, Path]] = {}
    for path in sorted(MIGRATIONS.glob("*.py")):
        if path.name.startswith("__"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            errors.append(f"Migration syntax {path.name}:{exc.lineno}: {exc.msg}")
            continue
        rev = down = None
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                key = node.targets[0].id
                if key in {"revision", "down_revision"}:
                    try:
                        value = ast.literal_eval(node.value)
                    except Exception:
                        value = None
                    if key == "revision":
                        rev = value
                    else:
                        down = value
        if not isinstance(rev, str):
            errors.append(f"Migration without literal revision: {path.name}")
            continue
        if isinstance(down, (tuple, list)):
            errors.append(f"Merge migration not supported by static gate: {path.name}")
            continue
        revisions[rev] = (down if isinstance(down, str) else None, path)
    children = {rev: 0 for rev in revisions}
    roots = []
    for rev, (down, path) in revisions.items():
        if down is None:
            roots.append(rev)
        elif down not in revisions:
            errors.append(f"Migration {path.name} references missing down_revision {down}")
        else:
            children[down] += 1
    heads = [rev for rev, child_count in children.items() if child_count == 0]
    if len(roots) != 1:
        errors.append(f"Expected one Alembic root, found {roots}")
    if len(heads) != 1:
        errors.append(f"Expected one Alembic head, found {heads}")
    config_source = (ROOT / "config.py").read_text(encoding="utf-8")
    if 'EXPECTED_SCHEMA_REVISION = discover_alembic_head(BASE_DIR)' not in config_source:
        errors.append('Config must derive EXPECTED_SCHEMA_REVISION from Alembic graph')
    return len(revisions), roots, heads


def check_legacy_templates(errors: list[str]):
    present = sorted(rel for rel in LEGACY_TEMPLATES if (ROOT / rel).exists())
    if present:
        errors.append("Legacy duplicate templates still present: " + ", ".join(present))
    return present


def check_visual_contract(errors: list[str]):
    shell = (ROOT / "templates/layouts/left_bar.html").read_text(encoding="utf-8")
    workspace = (ROOT / "templates/workspace/base.html").read_text(encoding="utf-8")
    launchpad = (ROOT / "templates/launchpad/index.html").read_text(encoding="utf-8")
    left_js = (ROOT / "static/js/left.js").read_text(encoding="utf-8")
    sales_core = (ROOT / "routes/sales/core.py").read_text(encoding="utf-8")
    sales_template = (ROOT / "templates/sales/create_sales.html").read_text(encoding="utf-8")
    required = [
        ("css/ui_unification.css" in shell, "Shared chrome does not load ui_unification.css"),
        ("viewport-fit=cover" in workspace, "Workspace viewport does not support safe areas"),
        ('<html lang="es" class="tablet-mode">' in launchpad, "Launchpad is not marked as tablet-mode"),
        ("!document.documentElement.classList.contains('tablet-mode')" in left_js, "Desktop sidebar collapse is active in tablet mode"),
        (
            "image_url = product_image_url(product)" in sales_core
            or "image_url = product_image_url(p)" in sales_core,
            "Sales catalog image fallback is unsafe",
        ),
        ("if (!response.ok)" in sales_template and "Array.isArray(products)" in sales_template, "POS catalog fetch does not validate its response"),
    ]
    for ok, message in required:
        if not ok:
            errors.append(message)


def check_javascript(errors: list[str]):
    node = shutil.which("node")
    files = [ROOT / "main.js"] + sorted((ROOT / "static" / "js").rglob("*.js"))
    if not node:
        return len(files), False
    for path in files:
        result = subprocess.run([node, "--check", str(path)], capture_output=True, text=True)
        if result.returncode:
            detail = (result.stderr or result.stdout).strip().splitlines()[-1] if (result.stderr or result.stdout).strip() else "syntax error"
            errors.append(f"JavaScript {path.relative_to(ROOT)}: {detail}")
    return len(files), True


def main() -> int:
    errors: list[str] = []
    check_python(errors)
    jinja_count = check_jinja(errors)
    endpoint_count, endpoint_refs, asset_refs = check_assets_and_endpoints(errors)
    migration_count, roots, heads = check_migrations(errors)
    check_legacy_templates(errors)
    check_visual_contract(errors)
    js_count, node_used = check_javascript(errors)

    print(f"Python: compileall {'OK' if not any(e.startswith('Python ') for e in errors) else 'FAIL'}")
    print(f"Jinja: {jinja_count} templates parsed")
    print(f"Endpoints: {endpoint_count} discovered / {endpoint_refs} url_for references checked")
    print(f"Static assets: {asset_refs} references checked")
    print(f"Alembic: {migration_count} revisions / roots={roots} / heads={heads}")
    print(f"JavaScript: {js_count} files {'checked with Node' if node_used else 'not checked (Node unavailable)'}")
    if errors:
        print("\nStatic release audit FAILED:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Static release audit OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
