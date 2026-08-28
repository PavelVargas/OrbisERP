#!/usr/bin/env python3
"""Static visual-consistency gate for OrbisERP.

This intentionally does not pretend to replace browser E2E. It catches the common
causes of visual regressions in templates: shell assets loaded in the wrong order,
undefined workspace components, legacy duplicate views, inline one-off styling in
core surfaces, obsolete block names and old off-brand accent colors.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
STATIC_CSS = ROOT / "static" / "css"

CORE_SURFACES = {
    "retail/overview.html",
    "retail/quality.html",
    "retail/warranties.html",
    "products/products.html",
    "products/detail.html",
    "sales/create_sales.html",
    "sales/detail_sales.html",
    "reports/retail_performance.html",
    "users/create_user.html",
    "users/edit_user.html",
    "users/users_profile.html",
    "users/permission_audit.html",
    "categories/category.html",
    "categories/create.html",
    "categories/edit.html",
    "company/plans.html",
    "reports/inventory_health.html",
    "transfers/by_warehouse.html",
    "transfers/list.html",
    "transfers/view_detail.html",
    "transfers/scanner_validation.html",
    "divisas/gestion.html",
    "reports/closings_history.html",
    "operations/data_center.html",
    "products/create.html",
    "products/edit.html",
    "warehouse/list.html",
    "governance/integrity.html",
}

LEGACY_DUPLICATES = {
    "sales/pending.html", "sales/quotes.html", "sales/sales.html",
    "workspace/activity.html", "workspace/executive.html", "cash/close.html",
    "warehouse/transfers_by_warehouse.html",
}

# Old accents that made parts of the product look like a different application.
FORBIDDEN_ACCENTS = {"#4f46e5", "#8b83ff", "#6366f1", "#4338ca", "#714b67"}
CLASS_RE = re.compile(r"class=[\"']([^\"']+)[\"']")
WORKSPACE_DEF_RE = re.compile(r"\.((?:workspace-)[A-Za-z0-9_-]+)")


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def main() -> int:
    errors: list[str] = []
    templates = sorted(TEMPLATES.rglob("*.html"))
    css_files = sorted(STATIC_CSS.rglob("*.css"))
    css_source = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in css_files)

    # 1) One authenticated shell, one predictable CSS order.
    authenticated = 0
    for path in templates:
        rel = path.relative_to(TEMPLATES).as_posix()
        source = path.read_text(encoding="utf-8", errors="replace")
        if "layouts/left_bar.html" in source and rel not in {"layouts/left_bar.html", "workspace/base.html"}:
            authenticated += 1
            if "extends 'workspace/base.html'" not in source and 'extends "workspace/base.html"' not in source:
                if "layouts/app_head_assets.html" not in source:
                    fail(errors, f"Authenticated legacy template does not load shell assets in <head>: {rel}")
                if "shell_assets_loaded = true" not in source:
                    fail(errors, f"Authenticated legacy template can duplicate shell assets: {rel}")

    app_head = (TEMPLATES / "layouts/app_head_assets.html").read_text(encoding="utf-8")
    if "js/tablet_runtime.js" not in app_head:
        fail(errors, "Authenticated shell must load static/js/tablet_runtime.js")

    launchpad = (TEMPLATES / "launchpad/index.html").read_text(encoding="utf-8")
    if "js/tablet_runtime.js" not in launchpad:
        fail(errors, "Tablet launchpad must load static/js/tablet_runtime.js")

    # Runtime CDN framework injection and duplicate common CSS are both
    # deployment/cascade hazards. Keep authenticated surfaces self-contained.
    common_assets = (
        "css/base_css/base.css", "css/left.css", "css/commercial.css",
        "css/ui_unification.css", "css/ux_polish.css", "css/ui_inline_migrations.css",
    )
    for path in templates:
        rel = path.relative_to(TEMPLATES).as_posix()
        source = path.read_text(encoding="utf-8", errors="replace")
        if "cdn.tailwindcss.com" in source:
            fail(errors, f"Runtime Tailwind CDN is forbidden: {rel}")
        if "layouts/app_head_assets.html" in source or "extends 'workspace/base.html'" in source or 'extends "workspace/base.html"' in source:
            if rel not in {"layouts/app_head_assets.html", "workspace/base.html"}:
                duplicated = [asset for asset in common_assets if source.count(asset)]
                if duplicated:
                    fail(errors, f"Authenticated template reloads common shell CSS ({', '.join(duplicated)}): {rel}")

    for css_path in css_files:
        source = css_path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"@import\s+(?:url\()?['\"]?/static/css/base_css/base\.css", source, re.I):
            fail(errors, f"Module CSS imports global base.css and can reset the cascade: {css_path.relative_to(ROOT)}")

    base = (TEMPLATES / "workspace/base.html").read_text(encoding="utf-8")
    common_pos = base.find("layouts/app_head_assets.html")
    workspace_pos = base.find("css/workspace.css")
    extra_pos = base.find("block extra_head")
    if not (0 <= common_pos < workspace_pos < extra_pos):
        fail(errors, "workspace/base.html must load shell -> workspace -> page-specific CSS in that order")

    # 2) Core modern surfaces should not carry one-off inline layout/color rules.
    for rel in sorted(CORE_SURFACES):
        path = TEMPLATES / rel
        if not path.exists():
            fail(errors, f"Core UI surface missing: {rel}")
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        inline = re.findall(r"\sstyle\s*=", source, flags=re.I)
        if inline:
            fail(errors, f"Core UI surface still has inline style attributes ({len(inline)}): {rel}")
        if "{% block subheading %}" in source:
            fail(errors, f"Obsolete workspace block 'subheading' in {rel}; use 'subtitle'")

    # 3) No stale duplicate view templates.
    for rel in sorted(LEGACY_DUPLICATES):
        if (TEMPLATES / rel).exists():
            fail(errors, f"Legacy duplicate template still present: {rel}")

    # 4) All workspace-* components referenced by templates must exist in CSS.
    used_workspace: set[str] = set()
    for path in templates:
        source = path.read_text(encoding="utf-8", errors="replace")
        for match in CLASS_RE.finditer(source):
            for cls in match.group(1).split():
                if cls.startswith("workspace-") and "{{" not in cls and "{%" not in cls:
                    used_workspace.add(cls)
    defined_workspace = set(WORKSPACE_DEF_RE.findall(css_source))
    missing = sorted(used_workspace - defined_workspace)
    if missing:
        fail(errors, "Undefined workspace component classes: " + ", ".join(missing))

    # 5) Remove old purple/indigo brand fragments from application templates/styles.
    for path in [*templates, *css_files]:
        source = path.read_text(encoding="utf-8", errors="replace").lower()
        found = sorted(color for color in FORBIDDEN_ACCENTS if color in source)
        if found:
            fail(errors, f"Off-brand accent {','.join(found)} in {path.relative_to(ROOT)}")

    if errors:
        print("UI consistency audit FAILED:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(
        "UI consistency audit OK: "
        f"templates={len(templates)} authenticated_shells={authenticated} "
        f"core_surfaces={len(CORE_SURFACES)} workspace_components={len(used_workspace)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
