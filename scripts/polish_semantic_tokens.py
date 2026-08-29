from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"

URL_FOR = re.compile(r"url_for\(\s*['\"]static['\"]\s*,\s*filename\s*=\s*['\"]([^'\"]+\.css)['\"]")
CSS_LITERAL = re.compile(r"(?:^|[\'\"(])(?:/static/)?(css/[A-Za-z0-9_./-]+\.css)")
CUSTOM_UI = re.compile(r"(?P<name>--(?!ui-)[\w-]+)\s*:\s*var\(--ui-[^)]+\)\s*;")

EXCLUDED_CSS = {
    "css/orbis_refined.css",
    "css/sales_css/create_sales.css",
    "css/orbis_print_v2.css",
    "css/scanner.css",
    "css/tablet_mode.css",
    "css/tablet_responsive.css",
    "css/tablet_experience.css",
}


def referenced_css() -> list[Path]:
    refs: set[str] = set()
    for tpl in TEMPLATES.rglob("*.html"):
        text = tpl.read_text("utf-8", errors="ignore")
        refs.update(URL_FOR.findall(text))
        refs.update(CSS_LITERAL.findall(text))
    return sorted(p for ref in refs if ref not in EXCLUDED_CSS and (p := STATIC / ref).exists())


def status_token(name: str, family: str) -> str:
    n = name.lower()
    if any(k in n for k in ("soft", "bg", "background")):
        return f"var(--ui-{family}-soft)"
    if any(k in n for k in ("line", "border", "stroke")):
        return f"var(--ui-{family}-line)"
    if family == "primary" and any(k in n for k in ("hover", "dark", "strong")):
        return "var(--ui-primary-hover)"
    return f"var(--ui-{family})"


def semantic_value(name: str) -> str | None:
    n = name.lower().replace("_", "-")

    # Semantic colors first.
    if any(k in n for k in ("danger", "error", "destructive", "red")):
        return status_token(n, "danger")
    if any(k in n for k in ("success", "green", "positive")):
        return status_token(n, "success")
    if any(k in n for k in ("warning", "warn", "yellow", "amber")):
        return status_token(n, "warning")
    if any(k in n for k in ("info", "cyan")):
        return status_token(n, "info")
    if any(k in n for k in ("primary", "accent", "orange", "purple", "violet", "indigo", "blue")):
        return status_token(n, "primary")

    # Neutrals / structure.
    if "shadow" in n:
        if any(k in n for k in ("lg", "float", "elevated", "hover")):
            return "var(--ui-shadow)"
        return "var(--ui-shadow-sm)"
    if any(k in n for k in ("border", "line", "stroke", "divider")):
        if "strong" in n:
            return "var(--ui-line-strong)"
        return "var(--ui-line)"
    if any(k in n for k in ("muted", "dim", "subtle", "secondary-text", "text-secondary", "text-2")):
        return "var(--ui-muted)"
    if any(k in n for k in ("text-soft", "soft-text", "text-tertiary")):
        return "var(--ui-text-soft)"
    if any(k in n for k in ("text", "ink", "foreground", "-fg", "fg-")) or n in {"--fg", "--color"}:
        return "var(--ui-text)"
    if any(k in n for k in ("input", "field")) and any(k in n for k in ("bg", "background", "surface")):
        return "var(--ui-surface-soft)"
    if any(k in n for k in ("surface-2", "surface2", "soft", "subtle", "tertiary", "panel-soft", "card-soft")):
        return "var(--ui-surface-soft)"
    if any(k in n for k in ("card", "panel", "surface", "popover", "modal")):
        return "var(--ui-surface)"
    if any(k in n for k in ("hover", "active")) and any(k in n for k in ("bg", "surface")):
        return "var(--ui-surface-hover)"
    if any(k in n for k in ("page", "canvas", "body", "app-bg")):
        return "var(--ui-bg)"
    if any(k in n for k in ("bg-main", "background-main", "bg-app")) or n in {"--bg", "--background"}:
        return "var(--ui-bg)"
    if any(k in n for k in ("bg-card", "background-card")):
        return "var(--ui-surface)"
    if any(k in n for k in ("bg-input", "background-input")):
        return "var(--ui-surface-soft)"
    if any(k in n for k in ("bg-hover", "background-hover")):
        return "var(--ui-surface-hover)"
    return None


def normalize_file(path: Path) -> int:
    text = path.read_text("utf-8", errors="ignore")
    changes = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal changes
        name = match.group("name")
        value = semantic_value(name)
        if not value:
            return match.group(0)
        new = f"{name}:{value};"
        if new != match.group(0):
            changes += 1
        return new

    new_text = CUSTOM_UI.sub(repl, text)
    # Any single-token border-side/outline left by previous migrations is invalid CSS.
    new_text = re.sub(
        r"(?<![-\w])(border(?:-(?:top|right|bottom|left))?)\s*:\s*(var\(--[^;)]+\))\s*;",
        r"\1:1px solid \2;",
        new_text,
        flags=re.I,
    )
    new_text = re.sub(
        r"(?<![-\w])outline\s*:\s*(var\(--[^;)]+\))\s*;",
        r"outline:2px solid \1;",
        new_text,
        flags=re.I,
    )
    if new_text != text:
        path.write_text(new_text, "utf-8")
    return changes


def main() -> None:
    touched = 0
    replacements = 0
    for path in referenced_css():
        n = normalize_file(path)
        if n or path.read_text("utf-8", errors="ignore"):
            # Track via content mtime is unnecessary; report semantic replacements only.
            replacements += n
            if n:
                touched += 1
    print(f"Semantic custom-property normalization: {replacements} replacements in {touched} CSS files")


if __name__ == "__main__":
    main()
