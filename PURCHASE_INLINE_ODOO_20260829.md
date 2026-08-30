# Purchase inline editor · 2026-08-29

La edición de órdenes de compra fue migrada a un patrón de documento con líneas inline inspirado en el flujo operativo de Odoo, manteniendo la identidad visual y navegación lateral de OrbisERP.

## Cambios
- El sidebar global permanece activo y sin modificaciones funcionales.
- Proveedor, fecha, destino y contenido se presentan como campos de documento, no como tarjetas aisladas.
- Las líneas existentes y la nueva línea comparten la misma tabla.
- Producto, variante, cantidad, UdM, precio unitario e ITBIS se introducen directamente en línea.
- El buscador typeahead de productos y sus contratos existentes se conservan.
- Los totales quedan integrados al pie del documento.
- La recepción de mercancía, cambio de proveedor, impuestos y eliminación de líneas mantienen sus rutas y permisos.
- Responsive y modo oscuro heredan los tokens de OrbisERP.

## Validación
- `scripts/static_release_audit.py`: OK.
- `scripts/ui_consistency_audit.py`: OK.
- `scripts/client_ui_audit.py`: OK.
- Contratos específicos de compras/typeahead/UdM: 4/4.
