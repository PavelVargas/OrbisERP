from __future__ import annotations
from pathlib import Path
import re
import colorsys
import tinycss2
from tinycss2.ast import QualifiedRule, AtRule, Declaration

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / 'templates'
STATIC = ROOT / 'static'

# Old brand/accent families that must no longer leak into the interface.
PRIMARY_SOLIDS = {
    '#f36b21','#df7419','#c96311','#ff9817','#ff7a2f','#ff9a58','#cf5c12','#d94f0d',
    '#ed6020','#f0933f','#e86f24','#faa200','#f97316','#f9a825','#c88716','#b56a13',
    '#e36a23','#f98a4d','#ffad62','#5b5bd6','#556fbd','#4b83e6','#3498db','#3976ad',
}
PRIMARY_SOFTS = {'#fff0e9','#fff3e8','#fff1e8','#fff7ed','#ffedd5'}

HEX8 = re.compile(r'#[0-9a-fA-F]{8}(?![0-9a-fA-F])')
HEX6 = re.compile(r'#[0-9a-fA-F]{6}(?![0-9a-fA-F])')


def active_css() -> list[Path]:
    names: set[str] = set()
    for p in TEMPLATES.rglob('*.html'):
        text = p.read_text(errors='ignore')
        names.update(re.findall(r"filename\s*=\s*['\"]([^'\"]+\.css)['\"]", text))
        names.update(re.findall(r'href=["\']/static/([^"\']+\.css)', text))
    excluded = {'css/orbis_refined.css', 'css/sales_css/create_sales.css'}
    out = []
    for name in sorted(names - excluded):
        p = STATIC / name
        if p.exists(): out.append(p)
    return out


def category_from_hex6(value: str) -> str:
    value = value.lower()
    if value in PRIMARY_SOLIDS: return 'primary'
    if value in PRIMARY_SOFTS: return 'primary-soft'
    h = value.lstrip('#')
    r,g,b = (int(h[i:i+2], 16)/255 for i in (0,2,4))
    hue,sat,light = colorsys.rgb_to_hls(r,g,b)
    hue *= 360
    if sat < .14:
        return 'neutral'
    if hue < 18 or hue >= 340:
        return 'danger'
    if 18 <= hue < 65:
        # Legacy orange was the old brand, but yellow/amber is semantic warning.
        if r > .85 and g < .72:
            return 'primary'
        return 'warning'
    if 65 <= hue < 175:
        return 'success'
    if 175 <= hue < 340:
        return 'primary'
    return 'neutral'


def soft_token(category: str) -> str:
    return {
        'primary':'var(--ui-primary-soft)', 'primary-soft':'var(--ui-primary-soft)',
        'success':'var(--ui-success-soft)', 'warning':'var(--ui-warning-soft)',
        'danger':'var(--ui-danger-soft)', 'neutral':'var(--ui-line)'
    }[category]


def line_token(category: str) -> str:
    return {
        'primary':'var(--ui-primary-line)', 'primary-soft':'var(--ui-primary-line)',
        'success':'var(--ui-success-line)', 'warning':'var(--ui-warning-line)',
        'danger':'var(--ui-danger-line)', 'neutral':'var(--ui-line)'
    }[category]


def main_token(category: str) -> str:
    return {
        'primary':'var(--ui-primary)', 'primary-soft':'var(--ui-primary)',
        'success':'var(--ui-success)', 'warning':'var(--ui-warning)',
        'danger':'var(--ui-danger)', 'neutral':'var(--ui-text-soft)'
    }[category]


def infer_category(value: str) -> str:
    lower = value.lower()
    if any(x in lower for x in ('primary','accent','violet','purple','orange','brand')): return 'primary'
    if any(x in lower for x in ('success','green')): return 'success'
    if any(x in lower for x in ('danger','error','red')): return 'danger'
    if any(x in lower for x in ('warning','amber','yellow')): return 'warning'
    for h in HEX6.findall(lower):
        cat = category_from_hex6(h)
        if cat != 'neutral': return cat
    return 'neutral'


def replace_legacy_colors(value: str) -> str:
    # Alpha colors become adaptive solid tokens so dark mode stays coherent.
    def alpha(m: re.Match[str]) -> str:
        base = m.group(0)[:7].lower()
        return soft_token(category_from_hex6(base))
    value = HEX8.sub(alpha, value)

    # Replace the old brand palette only. Semantic red/green/amber stays semantic.
    for old in sorted(PRIMARY_SOFTS, key=len, reverse=True):
        value = re.sub(re.escape(old), 'var(--ui-primary-soft)', value, flags=re.I)
    for old in sorted(PRIMARY_SOLIDS, key=len, reverse=True):
        value = re.sub(re.escape(old), 'var(--ui-primary)', value, flags=re.I)
    return value


def safe_value(name: str, original: str) -> str:
    category = infer_category(original)
    lower_name = name.lower()
    lower = original.lower()
    has_mix = 'color-mix(' in lower
    has_gradient = any(x in lower for x in ('linear-gradient(', 'radial-gradient(', 'conic-gradient('))
    if not (has_mix or has_gradient):
        return replace_legacy_colors(original)

    if lower_name.startswith('--'):
        if 'shadow' in lower_name: return 'none'
        if any(x in lower_name for x in ('border','line','outline')): return line_token(category)
        if any(x in lower_name for x in ('bg','background','surface','soft','subtle')): return soft_token(category)
        if any(x in lower_name for x in ('text','color','accent','primary','brand')): return main_token(category)
        return soft_token(category)

    if lower_name in {'box-shadow','text-shadow'}: return 'none'
    if lower_name in {'background-image','mask-image'}: return 'none'
    if lower_name.startswith('background'):
        return soft_token(category)
    if lower_name.startswith('border') or lower_name.startswith('outline'):
        return line_token(category)
    if lower_name in {'color','fill','stroke','caret-color','text-decoration-color'}:
        return main_token(category)
    if lower_name == 'filter': return 'none'
    # Last resort: remove unsupported decorative value rather than allow a legacy mix.
    return replace_legacy_colors(original).replace('color-mix', 'var') if not has_gradient else 'none'


def process_declaration_tokens(content):
    decls = tinycss2.parse_declaration_list(content, skip_comments=False, skip_whitespace=False)
    changed = False
    for d in decls:
        if not isinstance(d, Declaration):
            continue
        original = tinycss2.serialize(d.value).strip()
        updated = safe_value(d.name, original)
        if updated != original:
            d.value = tinycss2.parse_component_value_list(updated)
            changed = True
    return tinycss2.parse_component_value_list(tinycss2.serialize(decls)) if changed else content


def process_rules(rules):
    for rule in rules:
        if isinstance(rule, QualifiedRule):
            rule.content = process_declaration_tokens(rule.content)
        elif isinstance(rule, AtRule) and rule.content is not None:
            name = rule.at_keyword.lower()
            if name in {'media','supports','layer','container','keyframes','-webkit-keyframes'}:
                nested = tinycss2.parse_rule_list(rule.content, skip_comments=False, skip_whitespace=False)
                process_rules(nested)
                rule.content = tinycss2.parse_component_value_list(tinycss2.serialize(nested))
            elif name in {'font-face','page','property'}:
                rule.content = process_declaration_tokens(rule.content)
    return rules


def main():
    files = active_css()
    for p in files:
        text = p.read_text(errors='ignore')
        rules = tinycss2.parse_stylesheet(text, skip_comments=False, skip_whitespace=False)
        process_rules(rules)
        new = tinycss2.serialize(rules)
        # Final string safety for legacy direct colors in unusual constructs.
        new = replace_legacy_colors(new)
        p.write_text(new)
        print(p.relative_to(ROOT))

if __name__ == '__main__':
    main()
