from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_purchase_add_keeps_identical_products_as_independent_lines():
    source = (ROOT / 'routes/purchase/purchase.py').read_text(encoding='utf-8')
    marker = '# Cada alta representa una linea independiente de la orden.'
    assert marker in source
    block = source.split(marker, 1)[1].split('_refresh_order_totals(order)', 1)[0]
    assert 'PurchaseOrderItem.query.filter_by(' not in block
    assert 'item.quantity += quantity' not in block
    assert 'item = PurchaseOrderItem(' in block
    assert 'db.session.add(item)' in block
