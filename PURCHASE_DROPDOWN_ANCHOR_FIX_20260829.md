# Purchase dropdown anchor fix · 2026-08-29

Corrección del selector de productos en líneas continuas de órdenes de compra.

- El popover se posiciona antes de abrirse.
- Las coordenadas `top/left/right/bottom` se aplican como inline `!important` para que no sean anuladas por el CSS Top Layer.
- El dropdown queda anclado al campo Producto.
- Ancho: igual al input con límites razonables de viewport.
- Altura máxima: 264 px, con scroll interno.
- Abre hacia arriba automáticamente si no hay espacio debajo.
- Mantiene navegación con teclado y el flujo Producto -> Cantidad -> Enter.
