# Purchase product dropdown Top Layer fix · 2026-08-29

- El selector de productos de la línea continua usa `popover="manual"`.
- En navegadores compatibles se abre con `showPopover()`, por lo que se renderiza en la Top Layer del navegador y no puede ser recortado por la tabla, `overflow` ni stacking contexts normales.
- Posición calculada con `getBoundingClientRect()` y `position: fixed`.
- Abre debajo del input; si no hay espacio, abre arriba.
- Mantiene teclado ArrowUp/ArrowDown/Enter/Escape.
- Fallback para navegadores sin Popover API: se porta a `document.body` con `position: fixed`.
- Asset version: `20260829-lines4`.
