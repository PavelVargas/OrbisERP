from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.numeric import NumericValueError
from services.quantity import product_quantity

ROOT = Path(__file__).resolve().parents[1]


def read(rel):
    return (ROOT / rel).read_text(encoding='utf-8')


def test_purchase_product_entry_is_typeahead_not_native_select():
    template = read('templates/purchase/purchase_detail.html')
    assert 'id="productSearch"' in template
    assert 'id="productSuggestions"' in template
    assert 'type="hidden" name="product_id"' in template
    assert '<select name="product_id"' not in template


def test_purchase_sales_and_transfers_enforce_product_aware_quantities():
    purchase = read('routes/purchase/purchase.py')
    sales = read('routes/sales/core.py')
    transfers = read('routes/transfer_routes/transfer_routes.py')
    purchase_ui = read('templates/purchase/purchase_detail.html')
    sales_ui = read('templates/sales/create_sales.html')
    transfer_ui = read('templates/transfers/create.html')

    for source in (purchase, sales, transfers):
        assert 'product_quantity(' in source
        assert 'product=product' in source
    assert "qtyInput.step=fractional?'0.001':'1'" in purchase_ui
    assert 'step="${fractional?' in sales_ui
    assert "'0.001':'1'}\"" in sales_ui
    assert "product.allowFraction ? '0.001' : '1'" in transfer_ui

    unit = SimpleNamespace(sale_mode='UNIT', tracking='NONE', sale_uom=None, base_uom=None)
    weight = SimpleNamespace(sale_mode='WEIGHT', tracking='NONE', sale_uom=None, base_uom=None)
    serial_weight = SimpleNamespace(sale_mode='WEIGHT', tracking='SERIAL', sale_uom=None, base_uom=None)
    fractional_uom = SimpleNamespace(allow_fraction=True)

    assert product_quantity('2', product=unit) == Decimal('2')
    with pytest.raises(NumericValueError):
        product_quantity('0.5', product=unit)
    assert product_quantity('0.375', product=weight) == Decimal('0.375')
    assert product_quantity('0.125', product=unit, uom=fractional_uom) == Decimal('0.125')
    with pytest.raises(NumericValueError):
        product_quantity('0.5', product=serial_weight, uom=fractional_uom)
    with pytest.raises(NumericValueError):
        product_quantity('0.0001', product=weight)


def test_operational_user_requires_consistent_pos_branch_and_warehouse():
    users = read('routes/users/users.py')
    assert 'require_pos_context=(role == \'user\')' in users
    assert 'La terminal POS debe estar vinculada a una sucursal' in users
    assert 'pertenece a otro almacén' in users
    assert 'pertenece a otra sucursal' in users


def test_user_profile_exposes_sales_inventory_transfers_and_activity():
    route = read('routes/users/users.py')
    profile = read('templates/users/users_profile.html')
    assert "@users_bp.route('/users/<int:id>')" in route
    assert 'StockMovement.query.filter_by(company_id=company_id, user_id=target_user.id)' in route
    assert 'StockTransfer.created_by_id == target_user.id' in route
    for label in ('Ventas', 'Almacén', 'Transferencias', 'Actividad'):
        assert label in profile


def test_stock_and_transfer_actions_are_attributed_to_users():
    movement = read('models/stock_movement/stock_movement.py')
    transfer = read('models/stock_transfer/stock_transfer.py')
    migration = read('migrations/versions/f5a9c2d8e641_user_operational_attribution.py')
    assert "db.ForeignKey('users.id')" in movement
    assert 'created_by_id' in transfer and 'received_by_id' in transfer
    assert 'stock_movements' in migration and 'stock_transfers' in migration


def test_sensitive_user_admin_endpoints_have_explicit_permissions():
    users = read('routes/users/users.py')
    assert "has_permission('users.view')" in users
    assert "has_permission('audits.view')" in users
    assert "has_permission('users.reset_password')" in users
