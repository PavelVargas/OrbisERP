from __future__ import annotations

from pathlib import Path
import colorsys
import re
import tinycss2
from tinycss2.ast import AtRule, Declaration, QualifiedRule

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"

# Files that are already intentionally authored as canonical final profiles.
EXCLUDED = {
    "css/orbis_refined.css",
    "css/sales_css/create_sales.css",
    "css/orbis_print_v2.css",
    "css/tablet_mode.css",
    "css/tablet_responsive.css",
    "css/tablet_experience.css",
}

HEX_RE = re.compile(r"#[0-9a-fA-F]{3,6}(?![0-9a-fA-F])")
PX_RE = re.compile(r"(?<![\w.-])(-?\d+(?:\.\d+)?)px\b")

SPACE_SCALE = (0, 4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80, 96)
RADIUS_SCALE = (0, 4, 6, 8, 10, 12, 14, 16, 18)

PRIMARY_OLD = {
    "#f36b21", "#df7419", "#c96311", "#ff9817", "#ff7a2f", "#ff9a58",
    "#cf5c12", "#d94f0d", "#ed6020", "#f0933f", "#e86f24", "#faa200",
    "#f97316", "#5b5bd6", "#556fbd", "#4b83e6", "#3498db", "#3976ad",
    "#7c3aed", "#6d28d9", "#8b5cf6", "#9333ea", "#7e22ce",
}


def referenced_css() -> list[Path]:
    names: set[str] = set()
    for path in TEMPLATES.rglob("*.html"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        names.update(re.findall(r"filename\s*=\s*['\"]([^'\"]+\.css)['\"]", text))
        names.update(re.findall(r"href=['\"]/?static/([^'\"]+\.css)", text))
    out: list[Path] = []
    for name in sorted(names - EXCLUDED):
        path = STATIC / name
        if path.exists():
            out.append(path)
    return out


def expand_hex(value: str) -> str:
    value = value.lower()
    if len(value) == 4:
        return "#" + "".join(ch * 2 for ch in value[1:])
    return value


def rgb_info(value: str) -> tuple[float, float, float, float, float, float]:
    value = expand_hex(value)
    h = value[1:]
    r, g, b = (int(h[i:i+2], 16) / 255 for i in (0, 2, 4))
    hue, light, sat = colorsys.rgb_to_hls(r, g, b)
    # WCAG-ish relative luminance is unnecessary here; perceptual lightness is
    # sufficient for classifying legacy design colors into canonical tokens.
    return r, g, b, hue * 360, sat, light


def semantic_family(value: str) -> str:
    value = expand_hex(value)
    if value in PRIMARY_OLD:
        return "primary"
    _, _, _, hue, sat, _ = rgb_info(value)
    if sat < 0.16:
        return "neutral"
    if hue < 16 or hue >= 344:
        return "danger"
    if 16 <= hue < 72:
        return "warning"
    if 72 <= hue < 170:
        return "success"
    if 170 <= hue < 205:
        return "info"
    # Blue, indigo and legacy purple all collapse into one product accent.
    return "primary"


def token_for_color(value: str, prop: str) -> str:
    value = expand_hex(value)
    _, _, _, _, sat, light = rgb_info(value)
    family = semantic_family(value)
    prop = prop.lower()

    is_border = any(k in prop for k in ("border", "outline", "rule"))
    is_background = "background" in prop or prop.startswith("--") and any(k in prop for k in ("bg", "surface", "soft", "subtle"))
    is_text = prop in {"color", "fill", "stroke", "caret-color", "text-decoration-color"} or prop.endswith("-color") and not is_border and not is_background

    if family == "neutral":
        if is_border:
            return "var(--ui-line)"
        if is_background:
            if light >= 0.94:
                return "var(--ui-surface)"
            if light >= 0.80:
                return "var(--ui-surface-soft)"
            if light <= 0.28:
                return "var(--ui-bg)"
            return "var(--ui-surface-strong)"
        if is_text:
            if light >= 0.92:
                return "var(--ui-white)"
            if light <= 0.30:
                return "var(--ui-text)"
            if light <= 0.66:
                return "var(--ui-muted)"
            return "var(--ui-text-soft)"
        return "var(--ui-line)"

    prefix = {
        "primary": "primary",
        "success": "success",
        "warning": "warning",
        "danger": "danger",
        "info": "info",
    }[family]
    if is_border:
        if prefix == "info":
            return "var(--ui-info-line)"
        return f"var(--ui-{prefix}-line)"
    if is_background:
        if light > 0.78 or sat < 0.35:
            return f"var(--ui-{prefix}-soft)"
        return f"var(--ui-{prefix})"
    # Text/icons should use the semantic foreground, never a random shade.
    return f"var(--ui-{prefix})"


def normalize_colors(value: str, prop: str) -> str:
    return HEX_RE.sub(lambda m: token_for_color(m.group(0), prop), value)


def nearest(value: float, scale: tuple[int, ...]) -> int:
    return min(scale, key=lambda n: abs(n - value))


def normalize_spacing(value: str) -> str:
    def repl(match: re.Match[str]) -> str:
        raw = float(match.group(1))
        if raw == 0:
            return "0"
        sign = -1 if raw < 0 else 1
        amount = abs(raw)
        # Large layout offsets are deliberate. Rhythm normalization targets
        # component spacing, not viewport positioning.
        if amount > 100:
            return match.group(0)
        snapped = nearest(amount, SPACE_SCALE)
        return f"{sign * snapped}px"
    return PX_RE.sub(repl, value)


def normalize_radius(value: str) -> str:
    if "999" in value or "50%" in value:
        return value
    def repl(match: re.Match[str]) -> str:
        raw = abs(float(match.group(1)))
        if raw > 28:
            return "18px"
        return f"{nearest(raw, RADIUS_SCALE)}px"
    return PX_RE.sub(repl, value)


def normalize_font_size(value: str) -> str:
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)px\s*", value)
    if m and float(m.group(1)) < 12:
        return "12px"
    m = re.fullmatch(r"\s*(0?\.\d+)rem\s*", value)
    if m and float(m.group(1)) < 0.75:
        return "0.75rem"
    return value


def normalize_declaration(name: str, value: str) -> str:
    prop = name.lower()
    value = normalize_colors(value, prop)

    if prop in {"padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
                "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
                "gap", "row-gap", "column-gap"}:
        value = normalize_spacing(value)
    elif prop == "border-radius" or prop.endswith("-radius"):
        value = normalize_radius(value)
    elif prop == "font-size":
        value = normalize_font_size(value)
    elif prop == "font":
        def _font_px(match: re.Match[str]) -> str:
            amount = float(match.group(1))
            return "12px" if amount < 12 else match.group(0)
        value = re.sub(r"(?<![\w.-])(\d+(?:\.\d+)?)px\b", _font_px, value)
    elif prop == "box-shadow" and value.strip().lower() not in {"none", "0", "initial", "inherit"}:
        # Old per-module shadows were one of the largest sources of visual
        # inconsistency. Keep only a single quiet elevation vocabulary.
        if "inset" not in value.lower():
            value = "var(--ui-shadow-sm)"
    return value


def process_declarations(content):
    decls = tinycss2.parse_declaration_list(content, skip_comments=False, skip_whitespace=False)
    changed = False
    for decl in decls:
        if not isinstance(decl, Declaration):
            continue
        original = tinycss2.serialize(decl.value).strip()
        updated = normalize_declaration(decl.name, original)
        if updated != original:
            decl.value = tinycss2.parse_component_value_list(updated)
            changed = True
    return tinycss2.parse_component_value_list(tinycss2.serialize(decls)) if changed else content


def process_rules(rules):
    for rule in rules:
        if isinstance(rule, QualifiedRule):
            rule.content = process_declarations(rule.content)
        elif isinstance(rule, AtRule) and rule.content is not None:
            name = rule.at_keyword.lower()
            if name in {"media", "supports", "layer", "container", "keyframes", "-webkit-keyframes"}:
                nested = tinycss2.parse_rule_list(rule.content, skip_comments=False, skip_whitespace=False)
                process_rules(nested)
                rule.content = tinycss2.parse_component_value_list(tinycss2.serialize(nested))
            elif name in {"font-face", "page", "property"}:
                rule.content = process_declarations(rule.content)
    return rules


def main() -> None:
    files = referenced_css()
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        rules = tinycss2.parse_stylesheet(text, skip_comments=False, skip_whitespace=False)
        process_rules(rules)
        path.write_text(tinycss2.serialize(rules), encoding="utf-8")
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
