"""Strict parsers shared by money and inventory operations."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


MONEY_STEP = Decimal("0.01")


class BusinessRuleError(ValueError):
    """A safe validation message that may be shown to an end user."""


def positive_integer(value, field="Cantidad", *, maximum=1_000_000):
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError, TypeError, ValueError) as exc:
        raise BusinessRuleError(f"{field} debe ser un número entero válido.") from exc
    if not parsed.is_finite() or parsed != parsed.to_integral_value():
        raise BusinessRuleError(f"{field} debe ser un número entero válido.")
    maximum_decimal = Decimal(str(maximum))
    if parsed <= 0:
        raise BusinessRuleError(f"{field} debe ser mayor que cero.")
    if parsed > maximum_decimal:
        raise BusinessRuleError(f"{field} supera el máximo permitido ({maximum:,}).")
    try:
        return int(parsed)
    except (ValueError, TypeError, OverflowError) as exc:
        raise BusinessRuleError(f"{field} debe ser un número entero válido.") from exc


def non_negative_integer(value, field="Cantidad", *, maximum=1_000_000):
    if str(value).strip() in {"", "None"}:
        raise BusinessRuleError(f"{field} es obligatoria.")
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError, TypeError, ValueError) as exc:
        raise BusinessRuleError(f"{field} debe ser un número entero válido.") from exc
    if not parsed.is_finite() or parsed != parsed.to_integral_value() or parsed < 0:
        raise BusinessRuleError(f"{field} debe ser un entero igual o mayor que cero.")
    maximum_decimal = Decimal(str(maximum))
    if parsed > maximum_decimal:
        raise BusinessRuleError(f"{field} supera el máximo permitido ({maximum:,}).")
    try:
        return int(parsed)
    except (ValueError, TypeError, OverflowError) as exc:
        raise BusinessRuleError(f"{field} debe ser un entero igual o mayor que cero.") from exc


def positive_money(value, field="Importe", *, maximum=Decimal("9999999999.99")):
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError, TypeError, ValueError) as exc:
        raise BusinessRuleError(f"{field} debe ser un importe válido.") from exc
    if not amount.is_finite() or amount <= 0:
        raise BusinessRuleError(f"{field} debe ser mayor que cero.")
    if amount > maximum:
        raise BusinessRuleError(f"{field} supera el máximo permitido.")
    try:
        quantized = amount.quantize(MONEY_STEP, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError, OverflowError) as exc:
        raise BusinessRuleError(f"{field} tiene una precisión o magnitud no válida.") from exc
    if quantized != amount:
        raise BusinessRuleError(f"{field} admite como máximo 2 decimales.")
    return quantized


def tenant_id(value, field="Registro"):
    """Parse an identifier without accepting zero, negatives or booleans."""
    if isinstance(value, bool):
        raise BusinessRuleError(f"{field} no es válido.")
    return positive_integer(value, field, maximum=2_147_483_647)
