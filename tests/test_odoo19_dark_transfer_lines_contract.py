from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(relative):
    return (ROOT / relative).read_text(encoding='utf-8')

def test_dark_mode_uses_graphite_odoo_like_palette_and_orange_brand():
    css = read('static/css/orbis_refined.css')
    assert '--ui-bg: #191b1f;' in css
    assert '--ui-surface: #222428;' in css
    assert '--ui-surface-soft: #282b30;' in css
    assert '--ui-line: #34373d;' in css
    assert '--ui-primary: #ff7a45;' in css

def test_transfer_entry_is_continuous_keyboard_line_flow():
    template = read('templates/transfers/create.html')
    assert 'id="product-search"' in template
    assert 'id="transferQty"' in template
    assert 'function commitEntryLine()' in template
    assert "qtyInput.addEventListener('keydown'" in template
    assert 'commitEntryLine()' in template
    assert 'Agregar producto' not in template
    assert 'name="product_ids[]"' in template
    assert 'name="quantities[]"' in template
    assert "product.allowFraction ? '0.001' : '1'" in template

def test_transfer_stock_check_aggregates_duplicate_lines():
    template = read('templates/transfers/create.html')
    assert 'const grouped=new Map()' in template
    assert "grouped.set(row.dataset.productId" in template
    assert "rows.filter(row=>row.dataset.productId===productId)" in template
