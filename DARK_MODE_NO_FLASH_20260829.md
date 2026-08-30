# Dark mode no-flash fix · 2026-08-29

## Problema
La capa de movimiento anterior combinaba ocultación inicial del body, animaciones de entrada con opacity y View Transitions entre documentos. En navegaciones reales de Chromium esa combinación podía exponer un canvas blanco entre dos vistas oscuras.

## Corrección
- El tema persistente se sincroniza también en la cookie `orbis_theme`.
- Las vistas temáticas se sirven con un seed de tema desde el tag raíz cuando la cookie ya existe.
- El bootstrap de tema se ejecuta de forma síncrona antes del CSS externo.
- El canvas raíz se fuerza con `background-color` inline mediante JS y prioridad `important` antes del primer paint.
- El body ya no se oculta durante `theme-preload`.
- Las entradas de página conservan movimiento vertical pero ya no animan opacity.
- Se eliminaron las View Transitions cross-document para evitar el canvas intermedio blanco de Chromium.
- `html` y `body` no animan background-color al navegar/cambiar el tema.
- El fallback del sidebar nunca vuelve a activar `theme-preload` cuando ya existe body.
- Se mantiene `prefers-reduced-motion`.

## Validación
- `scripts/static_release_audit.py`: OK.
- `scripts/ui_consistency_audit.py`: OK.
- `scripts/client_ui_audit.py`: OK.
- Tests seleccionados de dark mode / visual / redesign: 20/20.
- Jinja: 118 plantillas parseadas.
