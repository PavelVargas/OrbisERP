from decimal import Decimal

from models.purchase.purchase_order_item import PurchaseOrderItem
from security import _FORM_RE


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

