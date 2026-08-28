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
OUTPUT = CSS_ROOT / "tablet_responsive.css"
REFERENCE_WIDTH = 1024.0
EXCLUDED = {OUTPUT.resolve()}

WIDTH_QUERY = re.compile(r"(?:min|max)-width\s*:", re.IGNORECASE)
WIDTH_CLAUSE = re.compile(
    r"\(\s*(min|max)-width\s*:\s*(\d+(?:\.\d+)?)px\s*\)",
    re.IGNORECASE,
)
UNSUPPORTED_QUERY = re.compile(
    r"(?:min|max)-height\s*:|prefers-|pointer\s*:|hover\s*:|print|speech",
    re.IGNORECASE,
)


def iter_css_files() -> list[Path]:
    return [
        path
        for path in sorted(CSS_ROOT.rglob("*.css"))
        if path.resolve() not in EXCLUDED
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
