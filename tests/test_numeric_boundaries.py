from decimal import Decimal
from types import SimpleNamespace

import pytest

from services.numeric import NumericValueError, bounded_decimal, finite_decimal, finite_int
from services.quantity import (
    base_quantity_from_factor,
    conversion_factor,
    loyalty_quantity,
    product_quantity,
)
from services.validation import BusinessRuleError, positive_integer, positive_money


@pytest.mark.parametrize("value", ["NaN", "sNaN", "Infinity", "-Infinity", "inf", "-inf"])
def test_non_finite_business_numbers_are_rejected(value):
    with pytest.raises(NumericValueError):
        finite_decimal(value)
    with pytest.raises(BusinessRuleError):
        positive_money(value)


def test_decimal_precision_is_rejected_instead_of_silently_rounded():
    assert bounded_decimal("12.30", places=2) == Decimal("12.30")
    with pytest.raises(NumericValueError):
        bounded_decimal("12.301", places=2)


def test_integer_parsers_reject_fractional_and_pathological_exponents():
    assert finite_int("42") == 42
    assert positive_integer("42") == 42
    for value in ("1.5", "1e999999999"):
        with pytest.raises(BusinessRuleError):
            positive_integer(value)
        with pytest.raises(NumericValueError):
            finite_int(value)


def test_product_quantity_uses_unit_weight_uom_and_serial_policy():
    unit = SimpleNamespace(sale_mode="UNIT", tracking="NONE", sale_uom=None, base_uom=None)
    weight = SimpleNamespace(sale_mode="WEIGHT", tracking="NONE", sale_uom=None, base_uom=None)
    fractional_uom = SimpleNamespace(allow_fraction=True)
    serial = SimpleNamespace(sale_mode="WEIGHT", tracking="SERIAL", sale_uom=None, base_uom=None)

    assert product_quantity("2", product=unit) == Decimal("2")
    with pytest.raises(NumericValueError):
        product_quantity("0.5", product=unit)

    assert product_quantity("0.375", product=weight) == Decimal("0.375")
    assert product_quantity("0.125", product=unit, uom=fractional_uom) == Decimal("0.125")
    with pytest.raises(NumericValueError):
        product_quantity("1.5", product=serial)
    with pytest.raises(NumericValueError):
        product_quantity("0.0001", product=weight)


def test_specialized_precision_is_preserved():
    assert loyalty_quantity("0.0001") == Decimal("0.0001")
    assert conversion_factor("0.000001") == Decimal("0.000001")
    with pytest.raises(NumericValueError):
        loyalty_quantity("0.00001")
    with pytest.raises(NumericValueError):
        conversion_factor("0.0000001")


def test_base_quantity_conversion_never_rounds_inventory_silently():
    assert base_quantity_from_factor("2", "0.125") == Decimal("0.250")
    with pytest.raises(NumericValueError):
        base_quantity_from_factor("1", "0.000001")
