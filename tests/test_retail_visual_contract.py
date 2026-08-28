from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_retail_shared_styles_cover_new_components():
    css = (ROOT / 'static/css/retail.css').read_text(encoding='utf-8')
    for selector in (
        '.retail-capabilities', '.retail-section', '.retail-inline-form',
        '.retail-grid-2', '.retail-grid-3', '.retail-table',
        '.product-tabs', '.product-tab', '.product-panel', '.variant-card',
    ):
        assert selector in css


def test_post_sale_screens_use_workspace_subtitle_contract():
    for rel in ('templates/retail/quality.html', 'templates/retail/warranties.html'):
        source = (ROOT / rel).read_text(encoding='utf-8')
        assert '{% block subtitle %}' in source
        assert '{% block subheading %}' not in source


def test_product_detail_does_not_redefine_retail_component_system_inline():
    source = (ROOT / 'templates/products/detail.html').read_text(encoding='utf-8')
    assert "css/retail.css" in source
    assert '<style nonce="{{ csp_nonce }}">' not in source
