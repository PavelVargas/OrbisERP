# GitHub Actions CI fix - 2026-08-30

Correcciones aplicadas a los 3 fallos reportados por `pytest -q -rs --ignore=tests/e2e`:

1. Se eliminaron 7 templates legacy/duplicados que no deben formar parte del release:
   - templates/cash/close.html
   - templates/sales/pending.html
   - templates/sales/quotes.html
   - templates/sales/sales.html
   - templates/workspace/activity.html
   - templates/workspace/executive.html
   - templates/warehouse/transfers_by_warehouse.html

2. Al desaparecer esos documentos HTML legacy también se resuelve el contrato global de `orbis_compact.css` para documentos HTML completos.

3. Se restauró la compatibilidad contractual del preview térmico conservando el diseño nuevo:
   - `ticketWidth` se mantiene.
   - vuelve a existir literalmente `Vista previa del ticket`.

Validación local de los tres tests que fallaban:

    5 passed

La suite completa no se pudo recolectar en este entorno porque no están instalados Flask / Flask-SQLAlchemy. El CI del repositorio sí instala esas dependencias.
