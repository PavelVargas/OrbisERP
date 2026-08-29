from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_polished_shell_loads_tablet_compatibility_in_head_and_final_sheet_per_document():
    head = read("templates/layouts/app_head_assets.html")
    base = read("templates/workspace/base.html")

    assert "css/tablet_mode.css" in head
    assert "css/tablet_responsive.css" in head
    assert "css/tablet_experience.css" in head
    assert "css/orbis_refined.css" in base
    assert base.index("block extra_head") < base.index("css/orbis_refined.css")
    assert "css/system_redesign.css" not in head


def test_commercial_summary_uses_canonical_application_shell():
    shell = read("templates/layouts/left_bar.html")
    dashboard = read("templates/dashboard/dashboard.html")
    final_css = read("static/css/orbis_refined.css")

    assert 'class="app-topbar"' in shell
    assert 'id="app-sidebar"' in shell
    assert 'body.orbis-app:not(.pos-page) > main' in final_css
    assert "Resumen comercial · OrbisERP" in dashboard
    assert "orbis_refined.css" in dashboard


def test_specialized_workstations_use_canonical_solid_tokens():
    pos = read("static/css/sales_css/create_sales.css")
    scanner = read("static/css/scanner.css")

    assert "--pos-primary: #2563eb" in pos
    assert "--pos-bg: #f5f7fa" in pos
    assert "--scan-accent: var(--ui-primary)" in scanner
    assert "--scan-bg: var(--ui-bg)" in scanner
    assert "--scan-text: var(--ui-text)" in scanner
    assert "rgba(" not in pos + scanner
    assert "color-mix(" not in pos + scanner
    assert not re.search(r"(?:linear|radial|conic)-gradient\s*\(", pos + scanner)


def test_public_entry_uses_same_canonical_visual_tokens():
    public_css = read("static/css/public.css")
    launchpad_css = read("static/css/launchpad.css")
    login = read("templates/login/login.html")
    launchpad = read("templates/launchpad/index.html")

    assert "var(--ui-primary)" in public_css
    assert "var(--ui-primary)" in launchpad_css
    assert "orbis_refined.css" in login
    assert "orbis_refined.css" in launchpad
    assert 'class="auth-page orbis-public"' in login
    assert 'class="orbis-launchpad"' in launchpad


def test_application_shell_uses_simple_sidebar_topbar_and_global_search():
    shell = read("templates/layouts/left_bar.html")
    script = read("static/js/left.js")

    assert 'id="app-sidebar" class="sidebar"' in shell
    assert 'class="app-topbar"' in shell
    assert 'id="global-search-modal"' in shell
    assert 'id="global-search-input"' in shell
    assert "global-search-modal" in script
    assert "enterprise-topbar" not in shell
