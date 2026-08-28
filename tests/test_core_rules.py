from decimal import Decimal

from models.purchase.purchase_order_item import PurchaseOrderItem
from security import _FORM_RE
from routes.purchase.purchase import _positive_integer, _positive_money
from services.csv_security import safe_csv_cell
from services.validation import (
    BusinessRuleError, non_negative_integer, positive_integer, positive_money,
)
import pytest


class Line:
    quantity = 2
    unit_cost = Decimal('118.00')
    tax_rate = Decimal('18.00')
    tax_included = True

    subtotal = property(PurchaseOrderItem.subtotal.fget)
    tax_amount = property(PurchaseOrderItem.tax_amount.fget)
    net_subtotal = property(PurchaseOrderItem.net_subtotal.fget)
    line_total = property(PurchaseOrderItem.line_total.fget)


def test_included_tax_is_extracted_without_increasing_total():
    line = Line()
    assert line.net_subtotal == Decimal('200.00')
    assert line.tax_amount == Decimal('36.00')
    assert line.line_total == Decimal('236.00')


def test_csrf_form_detection_is_case_insensitive():
    html = '<form class="x" METHOD="POST" action="/save">'
    assert _FORM_RE.search(html)


def test_purchase_quantity_accepts_integral_decimal_but_rejects_fraction():
    assert _positive_integer('1.00', 'Cantidad') == 1
    with pytest.raises(ValueError):
        _positive_integer('1.5', 'Cantidad')


def test_purchase_money_rejects_zero_negative_and_nan():
    assert _positive_money('10.129', 'Costo') == Decimal('10.13')
    for invalid in ('0', '-1', 'NaN'):
        with pytest.raises(ValueError):
            _positive_money(invalid, 'Costo')


@pytest.mark.parametrize('invalid', ('0', '-1', '1.5', 'NaN', 'Infinity', '', None))
def test_shared_inventory_quantity_rejects_invalid_values(invalid):
    with pytest.raises(BusinessRuleError):
        positive_integer(invalid)


def test_shared_inventory_quantity_accepts_integral_decimal():
    assert positive_integer('2.00') == 2
    assert non_negative_integer('0') == 0


@pytest.mark.parametrize('invalid', ('0', '-0.01', 'NaN', 'Infinity', ''))
def test_shared_money_rejects_non_positive_or_non_finite_values(invalid):
    with pytest.raises(BusinessRuleError):
        positive_money(invalid)


@pytest.mark.parametrize('dangerous', ('=1+1', '+SUM(A1:A2)', '-2+3', '@cmd', '\tformula'))
def test_csv_exports_neutralize_spreadsheet_formulas(dangerous):
    assert safe_csv_cell(dangerous).startswith("'")


def test_csv_exports_preserve_normal_values():
    assert safe_csv_cell('Producto seguro') == 'Producto seguro'
