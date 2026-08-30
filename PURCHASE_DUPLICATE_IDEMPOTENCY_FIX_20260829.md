# Purchase duplicate-line idempotency fix · 2026-08-29

## Problema

La orden de compra ya permitía guardar el mismo producto como líneas independientes, pero el formulario inline reutilizaba el `_idempotency_key` inyectado al cargar la página. Después de la primera línea, el segundo `Enter` podía recibir HTTP 409 con “Esta operación ya fue procesada”.

## Corrección

- Cada envío de la fila inline crea un `FormData` nuevo.
- Antes del `fetch`, `_idempotency_key` se reemplaza por una clave nueva y única.
- La protección global CSRF/idempotencia se conserva; no se ha desactivado seguridad.
- El backend sigue creando un `PurchaseOrderItem` nuevo por cada alta, incluso para el mismo producto/variante/UdM/impuesto.
- El flujo sigue siendo Producto → Enter → Cantidad → Enter → siguiente línea.
