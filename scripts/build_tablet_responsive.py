#!/usr/bin/env python3
"""Build the full-width tablet responsive compatibility stylesheet.

Browser media queries are evaluated against the physical viewport. Tablet mode
must keep using the complete viewport, so constraining the body to 1024px is
not acceptable. Instead, this builder treats 1024px as a *behavioral reference
width*:

* width queries that are true at 1024px are emitted as unconditional rules
  scoped to ``html.tablet-mode``;
* narrower max-width queries remain real media queries, also tablet-scoped;
* desktop-only min-width queries above 1024px are not mirrored.

The result is a full-width application that still chooses the same module
layouts a 1024px tablet would choose, even on a large desktop monitor.
"""
from __future__ import annotations

import re
from pathlib import Path

import tinycss2

ROOT = Path(__file__).resolve().parents[1]
CSS_ROOT = ROOT / "static" / "css"
TEMPLATES_ROOT = ROOT / "templates"
OUTPUT = CSS_ROOT / "tablet_responsive.css"
REFERENCE_WIDTH = 1024.0
EXCLUDED = {OUTPUT.resolve()}

URL_FOR_CSS = re.compile(
    r"url_for\(\s*['\"]static['\"]\s*,\s*filename\s*=\s*['\"]([^'\"]+\.css)['\"]"
)
DIRECT_CSS = re.compile(r"(?:^|['\"(])(?:/static/)?(css/[A-Za-z0-9_./-]+\.css)")

# Dedicated surfaces already own their responsive behavior and must not be
# copied into the authenticated tablet compatibility layer.
TABLET_MIRROR_EXCLUDED = {
    "css/tablet_responsive.css",
    "css/sales_css/create_sales.css",
    "css/orbis_print_v2.css",
}

WIDTH_QUERY = re.compile(r"(?:min|max)-width\s*:", re.IGNORECASE)
WIDTH_CLAUSE = re.compile(
    r"\(\s*(min|max)-width\s*:\s*(\d+(?:\.\d+)?)px\s*\)",
    re.IGNORECASE,
)
UNSUPPORTED_QUERY = re.compile(
    r"(?:min|max)-height\s*:|prefers-|pointer\s*:|hover\s*:|print|speech",
    re.IGNORECASE,
)


def referenced_css_paths() -> set[Path]:
    """Return stylesheets that are actually reachable from active templates.

    Previous builds mirrored media queries from every historical stylesheet in
    ``static/css``. That allowed abandoned redesign experiments to leak back
    into tablet mode even when no template loaded them. Tablet compatibility
    now follows the same active asset graph as the application.
    """
    refs: set[str] = set()
    for template in TEMPLATES_ROOT.rglob("*.html"):
        text = template.read_text(encoding="utf-8", errors="ignore")
        refs.update(URL_FOR_CSS.findall(text))
        refs.update(DIRECT_CSS.findall(text))
    return {
        (ROOT / "static" / ref).resolve()
        for ref in refs
        if ref not in TABLET_MIRROR_EXCLUDED and (ROOT / "static" / ref).exists()
    }


def iter_css_files() -> list[Path]:
    active = referenced_css_paths()
    return [
        path
        for path in sorted(CSS_ROOT.rglob("*.css"))
        if path.resolve() in active and path.resolve() not in EXCLUDED
    ]


def serialize(tokens) -> str:
    return tinycss2.serialize(tokens).strip()


def split_top_level_selectors(tokens) -> list[str]:
    groups: list[list] = [[]]
    for token in tokens:
        if token.type == "literal" and token.value == ",":
            groups.append([])
        else:
            groups[-1].append(token)
    return [serialize(group) for group in groups if serialize(group)]


def scope_selector(selector: str) -> str | None:
    selector = selector.strip()
    if not selector or ":not(.tablet-mode)" in selector:
        return None
    if selector.startswith(":root"):
        return "html.tablet-mode" + selector[len(":root"):]
    if selector.startswith("html"):
        if selector.startswith("html.tablet-mode"):
            return selector
        return "html.tablet-mode" + selector[len("html"):]
    return f"html.tablet-mode {selector}"


def scope_rule_list(content_tokens) -> str:
    rules = tinycss2.parse_rule_list(content_tokens, skip_comments=False, skip_whitespace=True)
    out: list[str] = []
    for rule in rules:
        if rule.type == "comment":
            continue
        if rule.type == "qualified-rule":
            selectors = [scope_selector(item) for item in split_top_level_selectors(rule.prelude)]
            selectors = [item for item in selectors if item]
            if not selectors:
                continue
            declarations = tinycss2.serialize(rule.content).strip()
            if declarations:
                out.append(f"{', '.join(selectors)} {{{declarations}}}")
            continue
        if rule.type == "at-rule":
            prelude = serialize(rule.prelude)
            if rule.content is None:
                out.append(f"@{rule.lower_at_keyword} {prelude};")
                continue
            # Nested conditional blocks can contain selectors and must remain
            # scoped. Keyframes do not use document selectors, so keep them.
            if rule.lower_at_keyword in {"supports", "layer", "container"}:
                nested = scope_rule_list(rule.content)
                if nested:
                    out.append(f"@{rule.lower_at_keyword} {prelude} {{\n{nested}\n}}")
            else:
                out.append(tinycss2.serialize([rule]).strip())
    return "\n".join(out)


def query_state(query: str, width: float = REFERENCE_WIDTH) -> tuple[bool, bool] | None:
    """Return (matches_reference, can_become_true_when_narrower)."""
    clauses = WIDTH_CLAUSE.findall(query)
    if not clauses:
        return None
    matches = True
    has_max_below_reference = False
    has_min_above_reference = False
    for kind, raw in clauses:
        value = float(raw)
        if kind.lower() == "max":
            matches = matches and width <= value
            if value < width:
                has_max_below_reference = True
        else:
            matches = matches and width >= value
            if value > width:
                has_min_above_reference = True
    can_become_true_when_narrower = has_max_below_reference and not has_min_above_reference
    return matches, can_become_true_when_narrower


def mirrored_blocks(path: Path) -> list[tuple[str, str, bool]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    rules = tinycss2.parse_stylesheet(text, skip_comments=False, skip_whitespace=False)
    blocks: list[tuple[str, str, bool]] = []
    for rule in rules:
        if rule.type != "at-rule" or rule.lower_at_keyword != "media" or rule.content is None:
            continue
        query = serialize(rule.prelude)
        if not WIDTH_QUERY.search(query) or UNSUPPORTED_QUERY.search(query):
            continue
        state = query_state(query)
        if state is None:
            continue
        matches_reference, can_become_true_when_narrower = state
        if not matches_reference and not can_become_true_when_narrower:
            continue
        content = scope_rule_list(rule.content)
        if not content:
            continue
        blocks.append((query, content, matches_reference))
    return blocks


def main() -> None:
    chunks = [
        "/* AUTO-GENERATED by scripts/build_tablet_responsive.py. DO NOT EDIT. */",
        "/* Full-width tablet mode; module breakpoints use a 1024px behavioral reference. */",
        "",
    ]
    total = 0
    reference_blocks = 0
    narrow_blocks = 0
    for path in iter_css_files():
        blocks = mirrored_blocks(path)
        if not blocks:
            continue
        relative = path.relative_to(ROOT).as_posix()
        chunks.append(f"/* {relative} */")
        for query, content, matches_reference in blocks:
            if matches_reference:
                chunks.append(f"/* reference match: {query} */")
                chunks.append(content)
                reference_blocks += 1
            else:
                chunks.append(f"@media {query} {{")
                chunks.append(content)
                chunks.append("}")
                narrow_blocks += 1
            chunks.append("")
            total += 1
    chunks.append(
        f"/* mirrored width-query blocks: {total}; reference: {reference_blocks}; narrower: {narrow_blocks} */"
    )
    OUTPUT.write_text("\n".join(chunks) + "\n", encoding="utf-8")
    print(
        f"Wrote {OUTPUT.relative_to(ROOT)} with {total} tablet breakpoint blocks "
        f"({reference_blocks} reference, {narrow_blocks} narrower)"
    )


if __name__ == "__main__":
    main()
