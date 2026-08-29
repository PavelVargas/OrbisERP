# OrbisERP UI 2.0 — migración visual completa

Fecha: 2026-08-29

## Alcance

Se migraron las 125 plantillas encontradas en el paquete de origen al nuevo sistema visual. Durante la certificación se verificó que 7 de esas plantillas eran duplicados legacy sin referencias activas y que los propios gates del repositorio exigían retirarlas. El paquete final contiene 118 plantillas activas.

## Dirección visual

- Interfaz más plana, limpia y consistente.
- Menos bordes y menos tarjetas anidadas.
- Jerarquía basada en espacios, superficie, tipografía y contraste.
- Naranja reservado para acciones y estados relevantes.
- Controles, tablas, filtros, estados, métricas, formularios y modales normalizados.
- Sidebar completamente refinado con navegación más calmada y compacta.
- Dark mode y tablet conservados.
- POS rediseñado mediante un perfil aislado para evitar interferir con su lógica.
- Login, registro, verificación y onboarding migrados al mismo lenguaje visual.
- PDF, recibos térmicos y reportes impresos usan un perfil independiente orientado a papel.

## Archivos de diseño nuevos

- `static/css/orbis_v2.css`: sistema visual principal.
- `static/css/orbis_print_v2.css`: perfil para documentos e impresión.
- `UI2_TEMPLATE_MANIFEST.json`: manifiesto de la migración.

## Compatibilidad funcional

No se cambiaron intencionalmente nombres de campos, endpoints, acciones de formularios, IDs, permisos, `data-*` hooks ni contratos JavaScript. La migración se hizo sobre estructura visual y estilos.

## Duplicados legacy retirados

- `templates/cash/close.html`
- `templates/sales/pending.html`
- `templates/sales/quotes.html`
- `templates/sales/sales.html`
- `templates/workspace/activity.html`
- `templates/workspace/executive.html`
- `templates/warehouse/transfers_by_warehouse.html`

Se comprobó que no tenían referencias activas. Su eliminación permite que el gate de consistencia visual del repositorio pase correctamente.

## Validación ejecutada

- Jinja: 118/118 plantillas activas parseadas.
- Python: `compileall` OK.
- Static release audit: OK.
- Endpoints: 256 descubiertos / 1222 referencias `url_for` revisadas.
- Assets estáticos: 202 referencias revisadas.
- Alembic: 27 revisiones; árbol válido.
- JavaScript: 15 archivos comprobados con Node.
- UI consistency audit: OK.
- Client UI audit: OK.
- Contratos visual/tablet/CSP/checkout seleccionados: 27/27 OK.

La suite completa de backend no pudo recolectarse en este contenedor porque no están instaladas las dependencias de ejecución `flask` y `flask_sqlalchemy`.
