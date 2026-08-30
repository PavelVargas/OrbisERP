# Purchase product dropdown fix · 2026-08-29

- El buscador de producto de las líneas continuas ya no renderiza el menú dentro de la celda de la tabla.
- El menú se monta en `document.body` y se posiciona como `fixed` junto al input.
- Evita recortes por `overflow`, filas de tabla y contenedores responsive.
- Ajusta posición al hacer scroll o resize y puede abrir hacia arriba si no hay espacio abajo.
- Mantiene teclado: flechas, Enter y Escape.
- Mantiene flujo Producto -> Cantidad -> Enter -> siguiente línea.
- Compatible con modo oscuro.
