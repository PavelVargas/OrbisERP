"""Quantity helpers for unit, weight and packaging-aware operations."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from services.numeric import NumericValueError, finite_decimal

QUANTITY_PLACES = 3
QUANTITY_STEP = Decimal("0.001")
MAX_QUANTITY = Decimal("999999999.999")
_MISSING = object()


def _field_label(field: str | None, field_name: str | None) -> str:
    return (field_name or field or "Cantidad").strip() or "Cantidad"


def _quantum(places: int) -> Decimal:
    if isinstance(places, bool) or not isinstance(places, int) or not 0 <= places <= 12:
        raise NumericValueError("Precisión de cantidad no válida.")
    return Decimal(1).scaleb(-places)


def _is_fractional_product(*, product=None, sale_mode=None, uom=None) -> bool:
    """Resolve the quantity policy for a product/UOM combination.

    Serial tracking always requires whole units. Weight products permit three
    decimals. An explicitly selected UOM may also permit fractions (for
    example, kilograms or metres) even when the product's default mode is UNIT.
    """
    tracking = str(getattr(product, "tracking", "") or "").strip().upper()
    if tracking in {"SERIAL", "SERIALIZED"}:
        return False

    mode = sale_mode
    if mode is None and product is not None:
        mode = getattr(product, "sale_mode", None)
    if str(mode or "").strip().upper() in {
        "WEIGHT", "FRACTIONAL", "DECIMAL", "VARIABLE_WEIGHT"
    }:
        return True

    if uom is not None:
        return bool(getattr(uom, "allow_fraction", False))

    if product is not None:
        for candidate in (
            getattr(product, "sale_uom", None),
            getattr(product, "base_uom", None),
        ):
            if candidate is not None and bool(getattr(candidate, "allow_fraction", False)):
                return True
        for attr in ("is_fractional", "allows_fractional_quantity", "allow_decimals"):
            marker = getattr(product, attr, None)
            if marker is not None:
                return bool(marker)
    return False


def to_quantity(
    value: Any,
    field: str = "Cantidad",
    *,
    allow_zero: bool = False,
    fractional: bool | None = True,
    places: int | None = None,
    field_name: str | None = None,
    default: Any = _MISSING,
    allow_blank: bool = False,
    maximum: Any = MAX_QUANTITY,
    product=None,
    sale_mode=None,
    uom=None,
) -> Decimal:
    """Parse, validate and quantize a business quantity.

    Existing callers may keep using the historical second positional ``field``
    argument and ``fractional=`` keyword. Newer callers can pass ``product`` and
    ``uom`` to derive the correct whole-unit/fractional policy automatically.
    Values with more precision than allowed are rejected rather than rounded.
    """
    label = _field_label(field, field_name)

    if value is None or (isinstance(value, str) and not value.strip()):
        if default is not _MISSING:
            value = default
        elif allow_blank:
            value = "0"
        else:
            raise NumericValueError(f"{label} es obligatoria.")

    parsed = finite_decimal(value, field_name=label)

    if product is not None or sale_mode is not None or uom is not None:
        fractional_allowed = _is_fractional_product(
            product=product, sale_mode=sale_mode, uom=uom
        )
    else:
        fractional_allowed = bool(fractional)

    effective_places = places if places is not None else (QUANTITY_PLACES if fractional_allowed else 0)
    if not fractional_allowed:
        effective_places = 0

    quantum = _quantum(effective_places)
    try:
        quantized = parsed.quantize(quantum, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError, OverflowError) as exc:
        raise NumericValueError(f"{label}: precisión o magnitud no válida.") from exc

    if quantized != parsed:
        if effective_places == 0:
            raise NumericValueError(f"{label} debe ser un número entero.")
        raise NumericValueError(
            f"{label} admite como máximo {effective_places} decimales."
        )

    if quantized < 0 or (quantized == 0 and not allow_zero):
        comparator = "igual o mayor que cero" if allow_zero else "mayor que cero"
        raise NumericValueError(f"{label} debe ser {comparator}.")

    max_value = finite_decimal(maximum, field_name=f"Máximo de {label}")
    if quantized > max_value:
        raise NumericValueError(f"{label} supera el máximo permitido ({max_value}).")
    return quantized


def positive_quantity(
    value: Any,
    field: str = "Cantidad",
    *,
    fractional: bool | None = True,
    places: int | None = None,
    field_name: str | None = None,
    default: Any = _MISSING,
    maximum: Any = MAX_QUANTITY,
    product=None,
    sale_mode=None,
    uom=None,
    **_kwargs,
) -> Decimal:
    return to_quantity(
        value,
        field,
        allow_zero=False,
        fractional=fractional,
        places=places,
        field_name=field_name,
        default=default,
        maximum=maximum,
        product=product,
        sale_mode=sale_mode,
        uom=uom,
    )


def non_negative_quantity(
    value: Any,
    field: str = "Cantidad",
    *,
    fractional: bool | None = True,
    places: int | None = None,
    field_name: str | None = None,
    default: Any = _MISSING,
    allow_blank: bool = False,
    maximum: Any = MAX_QUANTITY,
    product=None,
    sale_mode=None,
    uom=None,
    **_kwargs,
) -> Decimal:
    return to_quantity(
        value,
        field,
        allow_zero=True,
        fractional=fractional,
        places=places,
        field_name=field_name,
        default=default,
        allow_blank=allow_blank,
        maximum=maximum,
        product=product,
        sale_mode=sale_mode,
        uom=uom,
    )


def positive_integer(
    value: Any,
    field: str = "Cantidad",
    *,
    field_name: str | None = None,
    default: Any = _MISSING,
    maximum: int = 1_000_000,
    **_kwargs,
) -> int:
    parsed = positive_quantity(
        value,
        field,
        fractional=False,
        field_name=field_name,
        default=default,
        maximum=maximum,
    )
    return int(parsed)


def non_negative_integer(
    value: Any,
    field: str = "Cantidad",
    *,
    field_name: str | None = None,
    default: Any = _MISSING,
    maximum: int = 1_000_000,
    **_kwargs,
) -> int:
    parsed = non_negative_quantity(
        value,
        field,
        fractional=False,
        field_name=field_name,
        default=default,
        maximum=maximum,
    )
    return int(parsed)


def product_quantity(
    value: Any,
    field: str = "Cantidad",
    *,
    product=None,
    sale_mode=None,
    uom=None,
    allow_zero: bool = False,
    field_name: str | None = None,
    default: Any = _MISSING,
    maximum: Any = MAX_QUANTITY,
    **_kwargs,
) -> Decimal:
    return to_quantity(
        value,
        field,
        allow_zero=allow_zero,
        field_name=field_name,
        default=default,
        maximum=maximum,
        product=product,
        sale_mode=sale_mode,
        uom=uom,
    )


def conversion_factor(value: Any, field: str = "Factor de conversión") -> Decimal:
    return positive_quantity(value, field, fractional=True, places=6)


def loyalty_quantity(
    value: Any,
    field: str = "Valor de fidelización",
    *,
    allow_zero: bool = True,
) -> Decimal:
    parser = non_negative_quantity if allow_zero else positive_quantity
    return parser(value, field, fractional=True, places=4)


def as_decimal(value: Any) -> Decimal:
    """Convert an internal quantity to a finite Decimal; ``None`` means zero."""
    if value is None or value == "":
        return Decimal("0")
    return finite_decimal(value, field_name="Cantidad")


def display_decimal(value: Any, places: int = QUANTITY_PLACES) -> str:
    """Render a finite decimal with bounded precision and no trailing zeroes."""
    number = as_decimal(value).quantize(_quantum(places), rounding=ROUND_HALF_UP)
    if number == number.to_integral_value():
        return str(int(number))
    return format(number.normalize(), "f")


def display_quantity(value: Any) -> str:
    """Render stock quantities with the canonical three-decimal precision."""
    return display_decimal(value, QUANTITY_PLACES)


def base_quantity_from_factor(
    quantity: Any,
    factor: Any,
    field: str = "Cantidad base",
    *,
    allow_zero: bool = True,
    maximum: Any = MAX_QUANTITY,
) -> Decimal:
    """Convert a quantity using a stored factor without silent precision loss.

    Operational inventory columns use three decimal places. A conversion that
    would require more precision is rejected so a positive amount can never be
    rounded to zero or to a different stock balance unnoticed.
    """
    qty = as_decimal(quantity)
    conversion = finite_decimal(factor, field_name="Factor de conversión")
    if conversion <= 0:
        raise NumericValueError("Factor de conversión debe ser mayor que cero.")
    raw = qty * conversion
    quantized = raw.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    if quantized != raw:
        raise NumericValueError(
            f"{field}: la conversión admite como máximo 3 decimales de inventario."
        )
    if quantized < 0 or (not allow_zero and quantized == 0):
        comparator = "igual o mayor que cero" if allow_zero else "mayor que cero"
        raise NumericValueError(f"{field} debe ser {comparator}.")
    max_value = finite_decimal(maximum, field_name=f"Máximo de {field}")
    if quantized > max_value:
        raise NumericValueError(f"{field} supera el máximo permitido ({max_value}).")
    return quantized
