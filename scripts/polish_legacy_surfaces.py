from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / 'templates'
STATIC = ROOT / 'static'

URL_FOR = re.compile(r"url_for\(\s*['\"]static['\"]\s*,\s*filename\s*=\s*['\"]([^'\"]+\.css)['\"]")
CSS_REF = re.compile(r"(?:^|['\"(])(?:/static/)?(css/[A-Za-z0-9_./-]+\.css)")
RULE = re.compile(r"(?P<selector>[^{}]+)\{(?P<body>[^{}]*)\}")

EXCLUDE = {'css/orbis_refined.css', 'css/sales_css/create_sales.css', 'css/orbis_print_v2.css'}


def refs() -> list[tuple[str, Path]]:
    names: set[str] = set()
    for p in TEMPLATES.rglob('*.html'):
        text = p.read_text('utf-8', errors='ignore')
        names.update(URL_FOR.findall(text))
        names.update(CSS_REF.findall(text))
    return [(n, STATIC / n) for n in sorted(names) if (STATIC / n).exists() and n not in EXCLUDE]


def surface_for(selector: str) -> str:
    s = selector.lower()
    if any(k in s for k in ('backdrop', 'overlay')):
        return 'var(--ui-overlay)'
    if ':hover' in s or ':focus' in s:
        return 'var(--ui-surface-hover)'
    if re.search(r'(^|[\s>.#])(body|html)([\s.{:#]|$)', s):
        return 'var(--ui-bg)'
    if any(k in s for k in ('icon', 'avatar', 'placeholder', 'seller>span', 'person>span', 'empty>span')):
        return 'var(--ui-primary-soft)'
    if any(k in s for k in ('topbar', 'nav', 'dock', 'header')) and 'icon' not in s:
        return 'var(--ui-surface)'
    if any(k in s for k in ('thead', 'tabs', 'actions', 'search', 'stage', 'preview', 'column', 'inline-line', 'permission-group')):
        return 'var(--ui-surface-soft)'
    if any(k in s for k in ('panel', 'settings', 'card')):
        return 'var(--ui-surface)'
    return 'var(--ui-surface-soft)'


def fix_body(selector: str, body: str, filename: str) -> str:
    # Legacy migration had converted a range of neutral surfaces to --ui-line.
    # Restore them semantically based on the component role.
    if 'background:var(--ui-line)' in body or 'background: var(--ui-line)' in body:
        surface = surface_for(selector)
        body = re.sub(r'background\s*:\s*var\(--ui-line\)', f'background:{surface}', body)
    if 'background-color:var(--ui-line)' in body or 'background-color: var(--ui-line)' in body:
        surface = surface_for(selector)
        body = re.sub(r'background-color\s*:\s*var\(--ui-line\)', f'background-color:{surface}', body)

    # A soft status token is not a text color. This was another legacy palette artifact.
    body = re.sub(r'(?<![-\w])color\s*:\s*var\(--ui-danger-soft\)', 'color:var(--ui-danger)', body)
    body = re.sub(r'(?<![-\w])color\s*:\s*var\(--ui-warning-soft\)', 'color:var(--ui-warning)', body)
    body = re.sub(r'(?<![-\w])color\s*:\s*var\(--ui-info-soft\)', 'color:var(--ui-info)', body)
    body = re.sub(r'(?<![-\w])color\s*:\s*var\(--ui-primary-soft\)', 'color:var(--ui-primary)', body)

    # Structural/navigation text must remain neutral; semantic colors are reserved for states.
    structural = filename in {'css/left.css', 'css/app_final.css'} or any(k in selector.lower() for k in ('sidebar', 'topbar', 'tablet-section'))
    if structural:
        body = re.sub(r'(?<![-\w])color\s*:\s*var\(--ui-info\)', 'color:var(--ui-text)', body)
        body = re.sub(r'border(-(?:top|right|bottom|left))?\s*:\s*1px solid var\(--ui-danger-soft\)', lambda m: f'border{m.group(1) or ""}:1px solid var(--ui-line)', body)
        body = re.sub(r'border-color\s*:\s*var\(--ui-danger-soft\)', 'border-color:var(--ui-line)', body)
        body = re.sub(r'background\s*:\s*var\(--ui-danger-soft\)', 'background:var(--ui-surface-hover)', body)
    return body


def process(name: str, path: Path) -> int:
    text = path.read_text('utf-8', errors='ignore')
    changes = 0
    def repl(m: re.Match[str]) -> str:
        nonlocal changes
        sel, body = m.group('selector'), m.group('body')
        new_body = fix_body(sel, body, name)
        if new_body != body:
            changes += 1
        return f'{sel}{{{new_body}}}'
    out = RULE.sub(repl, text)
    # Public accent copy should follow the product primary instead of warning orange.
    if name in {'css/public.css','css/public_final.css'}:
        out = out.replace('color:var(--ui-warning)', 'color:var(--ui-primary)')
    # Launchpad featured cards use the same primary family in both themes.
    if name == 'css/launchpad.css':
        out = out.replace('background:var(--ui-danger-soft)', 'background:var(--ui-primary-soft)')
        out = out.replace('color:var(--ui-danger)', 'color:var(--ui-primary-text)')
        out = out.replace('color:var(--ui-white);box-shadow:none', 'color:var(--ui-text);box-shadow:none')
    if out != text:
        path.write_text(out, 'utf-8')
    return changes


def main() -> None:
    total = 0
    files = 0
    for name, path in refs():
        n = process(name, path)
        if n:
            files += 1
            total += n
    print(f'Legacy surface normalization: {total} rules in {files} referenced CSS files')

if __name__ == '__main__':
    main()
