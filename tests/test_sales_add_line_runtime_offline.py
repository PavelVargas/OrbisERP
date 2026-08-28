"""Execute the exact POS _add_line function without importing Flask.

The production project uses Flask-SQLAlchemy, which is intentionally not needed
for this regression test. We compile the function's AST and provide small fakes
for its collaborators so the pre-flush ORM relationship bug is exercised as
runtime Python, not only checked as source text.
"""
from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


class BusinessRuleError(ValueError):
    pass


class FakeQuery:
    def __init__(self, result=None):
        self.result = result
        self.filters = None

    def filter_by(self, **kwargs):
        self.filters = kwargs
        return self

    def first(self):
        return self.result


class FakeSession:
    def __init__(self):
        self.added = []
        self.flush_count = 0

    def add(self, item):
        self.added.append(item)

    def flush(self):
        self.flush_count += 1


class FakeSaleItem:
    query = FakeQuery()

    def __init__(self, **kwargs):
        for name, value in kwargs.items():
            setattr(self, name, value)
        sale = kwargs.get('sale')
        if sale is not None and self not in sale.items:
            sale.items.append(self)


class FakeProductType:
    SERVICE = 'SERVICE'


def decimal(value):
    return value if isinstance(value, Decimal) else Decimal(str(value))


def compile_add_line(*, existing=None, on_price=None):
    source = (ROOT / 'routes/sales/core.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == '_add_line'
    )
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)

    session = FakeSession()
    FakeSaleItem.query = FakeQuery(existing)

    def compatible_uoms(product):
        return list(product.allowed_uoms)

    def to_base(product, quantity, uom_id, *, purpose=None):
        assert purpose == 'sale'
        factors = {int(unit.id): decimal(factor) for unit, factor in product.allowed_uoms}
        if int(uom_id) not in factors:
            raise BusinessRuleError('Unidad no permitida')
        return decimal(quantity) * factors[int(uom_id)]

    def set_price(item, sale):
        if on_price is not None:
            return on_price(item, sale)
        assert item.product is not None
        item.price = Decimal('125.00')

    namespace = {
        'BusinessRuleError': BusinessRuleError,
        'as_decimal': decimal,
        'finite_decimal': decimal,
        '_compatible_uoms': compatible_uoms,
        'uom_to_base': to_base,
        'SaleItem': FakeSaleItem,
        '_sales_tax_for_product': lambda product, company_id: None,
        'db': SimpleNamespace(session=session),
        '_set_line_price': set_price,
        'ProductType': FakeProductType,
        'ensure_item_available': lambda item, sale_id=None: None,
        'reserve_serials_for_item': lambda item: None,
        'recalc_sale': lambda sale: None,
    }
    exec(compile(module, str(ROOT / 'routes/sales/core.py'), 'exec'), namespace)
    return namespace['_add_line'], session


def fixtures():
    unit = SimpleNamespace(id=10, name='Unidad')
    product = SimpleNamespace(
        id=1167,
        company_id=2,
        status=True,
        archived_at=None,
        sale_uom_id=10,
        base_uom_id=10,
        product_type='STOCKED',
        allowed_uoms=[(unit, Decimal('1'))],
    )
    warehouse = SimpleNamespace(id=3, company_id=2)
    variant = SimpleNamespace(id=5, product_id=1167, company_id=2, active=True)
    sale = SimpleNamespace(id=77, company_id=2, price_list_id=None, items=[])
    return sale, product, variant, warehouse


def test_new_line_has_relationships_before_price_resolution():
    sale, product, variant, warehouse = fixtures()
    seen = {}

    def price(item, current_sale):
        seen['product'] = item.product
        seen['variant'] = item.variant
        seen['warehouse'] = item.warehouse
        seen['sale'] = item.sale
        item.price = Decimal('125.00')

    add_line, session = compile_add_line(on_price=price)
    item = add_line(sale, product, variant, warehouse, Decimal('1'), 10)

    assert seen == {
        'product': product,
        'variant': variant,
        'warehouse': warehouse,
        'sale': sale,
    }
    assert item.product_id == product.id
    assert item.uom_factor == Decimal('1')
    assert session.added == [item]
    assert session.flush_count == 1


def test_existing_line_refreshes_stale_relationships_and_uom_factor():
    sale, product, variant, warehouse = fixtures()
    stale_product = SimpleNamespace(id=product.id, company_id=product.company_id)
    existing = SimpleNamespace(
        quantity=Decimal('2'), product=stale_product, product_id=product.id,
        variant=None, variant_id=None, warehouse=None, warehouse_id=warehouse.id,
        uom_id=10, uom_factor=Decimal('99'), price=Decimal('1'),
    )

    add_line, session = compile_add_line(existing=existing)
    item = add_line(sale, product, variant, warehouse, Decimal('1'), 10)

    assert item is existing
    assert existing.quantity == Decimal('3')
    assert existing.product is product
    assert existing.variant is variant
    assert existing.warehouse is warehouse
    assert existing.uom_factor == Decimal('1')
    assert session.added == []
    assert session.flush_count == 1


def test_direct_post_cannot_use_an_unconfigured_uom():
    sale, product, variant, warehouse = fixtures()
    add_line, session = compile_add_line()

    with pytest.raises(BusinessRuleError, match='no está habilitada'):
        add_line(sale, product, variant, warehouse, Decimal('1'), 999)

    assert session.added == []
    assert session.flush_count == 0


def test_existing_line_is_restored_when_pricing_fails():
    sale, product, variant, warehouse = fixtures()
    old_product = SimpleNamespace(id=product.id, company_id=product.company_id)
    old_warehouse = SimpleNamespace(id=warehouse.id, company_id=warehouse.company_id)
    existing = SimpleNamespace(
        quantity=Decimal('2'), product=old_product, product_id=product.id,
        variant=None, variant_id=None, warehouse=old_warehouse, warehouse_id=warehouse.id,
        uom_id=10, uom_factor=Decimal('2'), price=Decimal('88.50'),
    )
    sale.price_list_id = 15

    def fail_price(item, current_sale):
        current_sale.price_list_id = 99
        item.price = Decimal('999')
        raise BusinessRuleError('Precio inválido')

    add_line, session = compile_add_line(existing=existing, on_price=fail_price)
    with pytest.raises(BusinessRuleError, match='Precio inválido'):
        add_line(sale, product, variant, warehouse, Decimal('1'), 10)

    assert existing.quantity == Decimal('2')
    assert existing.product is old_product
    assert existing.variant is None
    assert existing.warehouse is old_warehouse
    assert existing.uom_factor == Decimal('2')
    assert existing.price == Decimal('88.50')
    assert sale.price_list_id == 15
    assert session.flush_count == 0
