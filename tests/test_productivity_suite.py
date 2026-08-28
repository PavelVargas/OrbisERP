from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from routes.sales.core import recalc_sale


ROOT = Path(__file__).resolve().parents[1]


def test_sale_discount_summary_remains_arithmetically_consistent():
    item = SimpleNamespace(
        quantity=1,
        price=Decimal('118.00'),
        tax_rate=Decimal('18.00'),
        tax_included=True,
    )
    promotion = SimpleNamespace(
        company_id=1,
        discount_type='PERCENT',
        value=Decimal('10.00'),
        is_available=lambda subtotal: subtotal >= Decimal('0.00'),
    )
    sale = SimpleNamespace(
        items=[item],
        company_id=1,
        promotion_id=1,
        promotion=promotion,
        subtotal=Decimal('0'),
        itbis=Decimal('0'),
        discount_amount=Decimal('0'),
        total=Decimal('0'),
    )

    recalc_sale(sale)

    assert sale.subtotal == Decimal('100.00')
    assert sale.itbis == Decimal('18.00')
    assert sale.discount_amount == Decimal('11.80')
    assert sale.total == Decimal('106.20')
    assert sale.subtotal + sale.itbis - sale.discount_amount == sale.total


def test_productivity_migration_is_single_configured_head():
    migration = (ROOT / 'migrations/versions/4c9e2f7a6b10_productivity_suite.py').read_text(encoding='utf-8')
    model = (ROOT / 'models/productivity.py').read_text(encoding='utf-8')

    assert "revision = '4c9e2f7a6b10'" in migration
    assert "down_revision = '3b7f9d5c2e81'" in migration
    assert 'uq_cash_sessions_open_user' in migration
    assert 'uq_cash_sessions_open_user' in model
    assert 'ck_promotions_date_range' in migration
    assert 'ck_promotions_date_range' in model


def test_private_storage_example_is_not_public_static():
    env_example = (ROOT / '.env.example').read_text(encoding='utf-8')
    assert 'STORAGE_ROOT=storage' in env_example
    assert 'STORAGE_ROOT=/app/static/uploads' not in env_example


def test_cash_register_enforces_open_and_close_permissions():
    source = (ROOT / 'routes/cash/cash.py').read_text(encoding='utf-8')
    assert "user.has_permission('cash.open')" in source
    assert "user.has_permission('cash.close')" in source
    assert 'except IntegrityError' in source


def test_document_upload_validates_related_entity_tenant():
    source = (ROOT / 'routes/workspace.py').read_text(encoding='utf-8')
    assert 'DOCUMENT_ENTITY_MODELS' in source
    assert 'model.query.filter_by(id=entity_id, company_id=company_id).first()' in source
    assert "raise ValueError('El registro relacionado no existe en esta empresa.')" in source


def test_new_company_gets_configurable_default_sales_tax():
    source = (ROOT / 'routes/company/company.py').read_text(encoding='utf-8')
    assert "name='ITBIS 18%'" in source
    assert 'price_included=True' in source
    assert 'is_default=True' in source
