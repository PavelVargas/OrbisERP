#!/usr/bin/env python3
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
errors = []


def require(condition, message):
    if not condition:
        errors.append(message)


class BlankTargetAudit(HTMLParser):
    def __init__(self, filename):
        super().__init__(convert_charrefs=True)
        self.filename = filename

    def handle_starttag(self, tag, attrs):
        if tag.lower() != 'a':
            return
        values = {key.lower(): (value or '') for key, value in attrs}
        if values.get('target', '').lower() != '_blank':
            return
        rel = {item.lower() for item in values.get('rel', '').split()}
        require('noopener' in rel, f'{self.filename} has target=_blank without rel=noopener')


head = (ROOT / 'templates/layouts/app_head_assets.html').read_text(encoding='utf-8')
left = (ROOT / 'templates/layouts/left_bar.html').read_text(encoding='utf-8')
tablet = (ROOT / 'static/js/tablet_runtime.js').read_text(encoding='utf-8')
leftjs = (ROOT / 'static/js/left.js').read_text(encoding='utf-8')
finalcss = (ROOT / 'static/css/app_final.css').read_text(encoding='utf-8')
launch = (ROOT / 'templates/launchpad/index.html').read_text(encoding='utf-8')
public_theme = (ROOT / 'static/js/public-theme-toggle.js').read_text(encoding='utf-8')
leftcss = (ROOT / 'static/css/left.css').read_text(encoding='utf-8')

require('js/theme-sync.js' in head, 'Authenticated head does not load theme-sync.js')
require('js/tablet_runtime.js' in head, 'Authenticated head does not load tablet_runtime.js')
require('<meta charset="UTF-8">' in head and 'viewport-fit=cover' in head,
        'El shell compartido no define charset/viewport antes de los recursos visuales')
require("root.classList.add('theme-preload', 'orbis-authenticated')" in head
        and head.index("root.classList.add('theme-preload', 'orbis-authenticated')") < head.index('css/quality-accessibility.css'),
        'El tema y el shell autenticado se aplican después del primer stylesheet y pueden producir un parpadeo')
require('shell_asset_version' in head and '20260827-tablet10' in head,
        'Los recursos globales no tienen una versión vigente de caché para distribuir correcciones visuales')
require('css/app_final.css' in left, 'Authenticated shell does not load final compatibility CSS')
require('css/tablet_mode.css' in left and 'css/tablet_responsive.css' in left,
        'Authenticated shell does not load the full-width tablet profile and mirrored responsive rules')
require('--tablet-profile-reference-width: 1024px' in (ROOT / 'static/css/tablet_mode.css').read_text(encoding='utf-8')
        and 'max-width: none !important' in (ROOT / 'static/css/tablet_mode.css').read_text(encoding='utf-8'),
        'Tablet profile does not keep a 1024px behavior reference while using the full viewport')
require('visualViewport' in tablet and 'tablet-keyboard-open' in tablet,
        'Tablet runtime does not handle the visual viewport/keyboard')
require('var(--tablet-vh,100dvh)' in leftcss,
        'Tablet shell does not consume runtime viewport height')
require('safeInternalUrl' in leftjs and 'results.replaceChildren' in leftjs,
        'Global search does not validate internal URLs and render safe DOM nodes')
require('js/public-theme-toggle.js' in launch and 'OrbisTheme.toggle' in public_theme,
        'Launchpad theme toggle is not synchronized with canonical theme runtime')
require('html.dark body > main' in finalcss,
        'Final CSS does not contain dark legacy compatibility rules')
require('html.tablet-mode.orbis-authenticated body:not(.pos-page) > main' in finalcss,
        'Final CSS does not contain the universal tablet application shell')

for path in sorted((ROOT / 'templates').rglob('*.html')):
    text = path.read_text(encoding='utf-8', errors='ignore')
    relative = path.relative_to(ROOT)
    if 'layouts/left_bar.html' in text:
        require(
            'layouts/app_head_assets.html' in text
            or "extends 'workspace/base.html'" in text
            or 'extends "workspace/base.html"' in text
            or "extends 'backoffice/base.html'" in text
            or 'extends "backoffice/base.html"' in text,
            f'{relative} uses authenticated navigation without shared head assets/base',
        )
    parser = BlankTargetAudit(relative)
    parser.feed(text)

if errors:
    print('CLIENT_UI_AUDIT: FAILED')
    for error in errors:
        print('-', error)
    raise SystemExit(1)

print('CLIENT_UI_AUDIT: OK')
print('Verified canonical dark mode, tablet runtime, legacy compatibility, safe external tabs and DOM-safe global-search rendering.')
