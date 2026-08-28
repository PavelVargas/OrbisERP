"""Strict numeric parsers for HTTP and service boundaries.

``decimal.Decimal`` accepts special values such as NaN and Infinity. They are
not valid business values and can otherwise fail later during comparisons,
quantization, serialization, or database writes. These helpers reject them at
the boundary with a user-safe validation error.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from services.validation import BusinessRuleError


class NumericValueError(BusinessRuleError):
    """Raised when user-supplied numeric data is malformed or non-finite."""


def finite_decimal(
    value: Any = "0",
    *,
    field_name: str | None = None,
    allow_blank: bool = False,
    default: Any | None = None,
) -> Decimal:
    """Return a finite :class:`Decimal` or raise ``NumericValueError``.

    Blank input is rejected unless ``allow_blank`` is explicitly enabled. A
    ``default`` is only used in that explicit blank-input mode; malformed and
    non-finite values are never converted silently.
    """
    label = field_name or "Valor"
    if value is None or (isinstance(value, str) and not value.strip()):
        if not allow_blank:
            raise NumericValueError(f"{label}: se requiere un número.")
        value = "0" if default is None else default

    # Decimal(str(...)) gives consistent behavior for floats, ints and form
    # strings and avoids Decimal(float)'s binary-expansion surprise.
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError, AttributeError, OverflowError) as exc:
        raise NumericValueError(f"{label}: número no válido.") from exc

    if not parsed.is_finite():
        raise NumericValueError(f"{label}: NaN e infinito no están permitidos.")
    return parsed


def finite_int(value: Any, *, field_name: str | None = None) -> int:
    """Return a strict finite integer without accepting decimal fractions.

    The exponent is bounded before converting to :class:`int`; otherwise an
    input such as ``1e999999999`` can make Python spend excessive CPU and
    memory constructing an integer that the caller will reject afterwards.
    """
    label = field_name or "Valor"
    parsed = finite_decimal(value, field_name=label)
    if parsed != parsed.to_integral_value():
        raise NumericValueError(f"{label}: debe ser un número entero.")
    if parsed and parsed.copy_abs().adjusted() > 17:
        raise NumericValueError(f"{label}: entero fuera del rango permitido.")
    try:
        return int(parsed)
    except (ValueError, TypeError, OverflowError) as exc:
        raise NumericValueError(f"{label}: entero no válido.") from exc


def bounded_decimal(
    value: Any,
    *,
    field_name: str | None = None,
    places: int = 2,
    minimum: Any | None = None,
    maximum: Any | None = None,
    allow_blank: bool = False,
    default: Any | None = None,
) -> Decimal:
    """Parse a finite decimal with exact precision and optional bounds.

    User input with more fractional digits than ``places`` is rejected instead
    of being silently rounded. This keeps the HTML step, service contract and
    database scale aligned.
    """
    from decimal import ROUND_HALF_UP

    label = field_name or "Valor"
    if isinstance(places, bool) or not isinstance(places, int) or not 0 <= places <= 12:
        raise NumericValueError(f"{label}: precisión no válida.")
    parsed = finite_decimal(
        value,
        field_name=label,
        allow_blank=allow_blank,
        default=default,
    )
    quantum = Decimal(1).scaleb(-places)
    try:
        quantized = parsed.quantize(quantum, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError, OverflowError) as exc:
        raise NumericValueError(f"{label}: precisión o magnitud no válida.") from exc
    if quantized != parsed:
        suffix = "entero" if places == 0 else f"con máximo {places} decimales"
        raise NumericValueError(f"{label}: debe ser un número {suffix}.")
    if minimum is not None:
        low = finite_decimal(minimum, field_name=f"Mínimo de {label}")
        if quantized < low:
            raise NumericValueError(f"{label}: debe ser igual o mayor que {low}.")
    if maximum is not None:
        high = finite_decimal(maximum, field_name=f"Máximo de {label}")
        if quantized > high:
            raise NumericValueError(f"{label}: debe ser igual o menor que {high}.")
    return quantized
