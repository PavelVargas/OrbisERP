# POS image fix · 2026-08-29

Ajuste puntual sobre el POS de ventas:

- Galería unificada con el diseño POLISHED.
- Tarjetas más anchas para dar prioridad visual al producto.
- Lienzo de imagen proporcional y consistente.
- Las imágenes se muestran completas, centradas y respetando su proporción.
- Se eliminan escalados que pudieran cortar la fotografía: `width/height: auto`, `max-width/max-height: 100%`, `object-fit: contain`.
- Responsive ajustado para escritorio, tablet y móvil.
- No se modificó la lógica de venta, carrito, unidades, almacén, cliente ni checkout.

Validación:
- Python compileall: OK.
- Jinja: 118 plantillas parseadas.
- Static release audit: OK.
- 257 endpoints / 1233 `url_for` / 205 assets / 27 migraciones / 15 JS verificados.
