# Ordenes de compra - lineas continuas

La edicion de productos de la orden de compra ahora funciona como una hoja de lineas continua:

- no existe boton "Agregar producto";
- la ultima fila siempre es una linea vacia de captura;
- al seleccionar un producto, el foco pasa a Cantidad;
- Enter en Cantidad guarda la linea por AJAX, sin recargar la vista;
- al terminar, se crea/focaliza inmediatamente la siguiente linea vacia;
- precio de compra, UdM, variante e impuesto se autocompletan y siguen siendo editables;
- si la misma combinacion producto/variante/UdM/impuesto ya existe, la cantidad se acumula y la fila se actualiza en sitio;
- subtotal, ITBIS, total y resumen de contenido se actualizan sin recargar;
- el sidebar y la estructura general de OrbisERP no se modifican.

Archivos principales:

- `templates/purchase/purchase_detail.html`
- `templates/purchase/_purchase_line.html`
- `static/css/order_css/purchase_odoo.css`
- `routes/purchase/purchase.py`

Validacion ejecutada:

- `scripts/static_release_audit.py`: OK
- contratos de compra/typeahead/UdM: 8/8
- JavaScript inline de la orden: sintaxis Node OK
