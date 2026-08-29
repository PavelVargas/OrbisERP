# GitHub CI fix - 2026-08-29

Corregido el fallo de colección de `tests/test_core_rules.py`.

## Causa

`tests/test_core_rules.py` importa `_positive_integer` y `_positive_money` desde
`routes.purchase.purchase`. `_positive_integer` había desaparecido durante una
refactorización y `_positive_money` ya no conservaba el contrato histórico de
redondeo monetario esperado por el test.

## Corrección

- Restaurado `_positive_integer(raw_value, field_name)`.
- Acepta decimales integrales como `1.00`.
- Rechaza fracciones, cero, negativos y valores no finitos.
- `_positive_money` vuelve a normalizar importes con `ROUND_HALF_UP` a 2 decimales.
- Mantiene rechazo de cero, negativos, `NaN`, infinito y valores fuera de rango.

No se modificaron los tests para ocultar el fallo.

## Verificación disponible en el runner

- `python -m compileall -q routes/purchase/purchase.py services`: OK.
- Contrato equivalente a `tests/test_core_rules.py` para ambos helpers: OK.

El runner aislado no tiene acceso de red ni Flask/Flask-SQLAlchemy instalados, por
lo que no puede ejecutar aquí la suite completa. El workflow de GitHub instala
`requirements-dev.txt` antes de ejecutar `pytest`.
