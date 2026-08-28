from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
errors = []


def read(relative):
    path = ROOT / relative
    if not path.exists():
        errors.append(f"Missing required file: {relative}")
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


template = read("templates/transfers/scanner_validation.html")
css = read("static/css/scanner.css")
script = read("static/js/scanner.js")
sidebar = read("templates/layouts/left_bar.html")
routes = read("routes/transfer_routes/transfer_routes.py")
permissions = read("permissions.py")

checks = [
    ('<html lang="es" class="scanner-dark' in template, "Scanner root dark class is missing."),
    ('<body class="scanner-mode-page">' in template, "Scanner body class is missing."),
    ('meta name="color-scheme" content="dark"' in template, "Dark color-scheme metadata is missing."),
    ("This page intentionally remains dark" in css, "Scanner CSS does not declare the fixed dark workstation contract."),
    ("--scan-bg: #0c0e11" in css, "Scanner dark background token is missing."),
    ("background: var(--scan-bg) !important" in css, "Scanner body does not override the global important light background."),
    ("padding: 30px clamp(18px, 3.2vw, 48px) 42px !important" in css, "Scanner layout does not override the global important main spacing."),
    ('#manual-scan-form > button[type="submit"]' in css and "background: var(--scan-accent) !important" in css, "Scanner submit actions do not override the global important button theme."),
    ("body.scanner-mode-page .status-badge.status-complete" in css, "Scanner completion badge is still vulnerable to the global badge theme."),
    ("body.scanner-mode-page .sku-tag" in css, "Scanner SKU tag is still vulnerable to the global badge theme."),
    ("v='20260825-dark5'" in template, "Scanner asset cache version was not updated."),
    ("--scan-accent: #f36b21" in css, "Scanner is not connected to the orange brand token."),
    ("--primary: #10b981" not in css, "Scanner overrides the global primary token with green."),
    ("static', filename='js/scanner.js'" in template, "Scanner JavaScript is not loaded as a dedicated asset."),
    ("scan_codes" in script, "Scanner client does not use the server-provided barcode set."),
    ("WAITING_QUANTITY" in script, "Fractional quantity flow is missing."),
    ("ProductBarcode.query.filter_by" in routes, "ProductBarcode support is missing from the scanner API."),
    ("user.warehouse_id != transfer.to_warehouse_id" in routes, "Destination warehouse restriction is missing."),
    ("request.referrer" not in routes, "Receive flow still trusts request.referrer."),
    ("not request.path.startswith('/transfers/scanner')" in sidebar, "Transfer parent remains active on scanner routes."),
    ("request.path.startswith('/transfers/scanner-mode')" in sidebar, "Scanner active state is not explicit."),
    ("'transfer_bp.receive_transfer': ('transfers.receive', 'transfers.scanner')" in permissions, "Scanner operators cannot complete the receive endpoint."),
]
for ok, message in checks:
    if not ok:
        errors.append(message)

marker = "ORBIS_SCANNER_THEME_HARDENING_20260825"
for path in (ROOT / "static/css").rglob("*.css"):
    text = path.read_text(encoding="utf-8", errors="replace")
    if marker in text:
        errors.append(f"Legacy scanner block remains in {path.relative_to(ROOT)}")
    if path.name != "scanner.css" and re.search(r"--primary\s*:\s*(?:#10b981|#059669|#047857|#34d399)", text, re.I):
        # Existing unrelated modules are reported only when their file name or body references the scanner.
        if "scanner" in text.lower() or "scanner" in path.as_posix().lower():
            errors.append(f"{path.relative_to(ROOT)} overrides scanner primary with green.")

if errors:
    print("TRANSFER_SCANNER_AUDIT: FAIL")
    for error in errors:
        print(" - " + error)
    sys.exit(1)

print("TRANSFER_SCANNER_AUDIT: OK")
print("Fixed dark theme, exclusive navigation, product barcode, fractional quantity and safe receive flow verified.")
