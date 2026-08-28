"""Consistent monetary helpers.

Database money columns use :class:`decimal.Decimal`.  Keeping exchange-rate
math in Decimal avoids the ``Decimal / float`` crashes that are otherwise easy
to introduce in templates and reporting routes.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

MONEY_QUANT = Decimal('0.01')
ONE = Decimal('1')
ZERO = Decimal('0')


def as_decimal(value, default=ZERO):
    """Return *value* as a finite Decimal without accepting binary-float math."""
    if value is None or value == '':
        return Decimal(str(default))
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(str(default))
    if not result.is_finite():
        return Decimal(str(default))
    return result


def money(value, default=ZERO):
    """Normalize a value to two decimal places using commercial rounding."""
    return as_decimal(value, default).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def exchange_rate(value):
    """Return a safe positive exchange rate; invalid/non-positive values become 1."""
    rate = as_decimal(value, ONE)
    return rate if rate > ZERO else ONE


def from_base(value, rate):
    """Convert a base-currency amount to the selected display currency."""
    return money(as_decimal(value) / exchange_rate(rate))


def to_base(value, rate):
    """Convert a selected-currency amount back to the base currency."""
    return money(as_decimal(value) * exchange_rate(rate))
