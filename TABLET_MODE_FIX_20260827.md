# Tablet mode - full-width shell revision (2026-08-27)

## Required behavior

Tablet mode is a complete application state, not a desktop preview and not a centered 1024px canvas.

- The desktop sidebar is hidden for the whole authenticated session.
- The application uses 100% of the physical viewport width.
- A bottom dock represents the main system sections: Inicio, Ventas, Inventario, Compras, Control and Ajustes.
- Section buttons open a touch sheet populated from the same permission-filtered links used by the desktop sidebar.
- The top tablet bar remains available for apps, global search, profile and exit-to-desktop.
- Forms, grids, tables, cards and module layouts keep tablet behavior even when tablet mode is opened on a large desktop monitor.

## Responsive model

1024px is now a behavioral reference only. `scripts/build_tablet_responsive.py` evaluates module width media queries against a 1024px reference and emits tablet-scoped compatibility rules. The body is never constrained to 1024px.

This means a 1512px monitor in tablet mode still uses all 1512px of space, while module decisions such as two-column tablet grids remain the same decisions they would make around 1024px.

## Main files

- `templates/layouts/left_bar.html`: section dock and section sheet.
- `static/js/tablet_runtime.js`: viewport state, full-width profile, section dock population and keyboard handling.
- `static/css/tablet_mode.css`: global full-width tablet contract and desktop sidebar suppression.
- `static/css/left.css`: tablet top bar, dock and section sheet interaction surface.
- `static/css/app_final.css`: universal authenticated tablet geometry.
- `static/css/tablet_responsive.css`: generated tablet-scoped module breakpoints.
- `scripts/build_tablet_responsive.py`: 1024px behavioral breakpoint compiler.

## Validation

Static contract tests verify the session flag, full-width profile, sidebar replacement, section dock and generated breakpoint behavior. A Chromium smoke fixture at a 1512x900 viewport verifies that the body, main and tablet top bar are 1512px wide, the sidebar is hidden, a 1024px reference is retained, dashboard metrics use the tablet two-column layout, and the Ventas section opens a populated tablet sheet.

## Tablet experience v9 — persistence, theme, compact dock and motion

Corrección aplicada tras validación visual del 27 Aug 2026:

- **Persistencia real entre módulos:** `orbis_tablet_mode` se mantiene como preferencia de UI durante 30 días y `app.py` sincroniza esa preferencia con `session['tablet_mode']` antes de renderizar cualquier ruta autenticada. El modo solo se desactiva al usar explícitamente **Escritorio**.
- **Respaldo antes del primer paint:** `app_head_assets.html` combina sesión, cookie y `localStorage` antes de cargar la interfaz. El chrome tablet se incluye siempre en el DOM autenticado y permanece oculto en escritorio; así no aparece la sidebar si la sesión necesita reconstruir contexto.
- **Tema correcto:** `static/css/tablet_experience.css` elimina las superficies negras hardcodeadas de topbar, dock y section sheet. En tema claro usa `--bg-card`, `--bg-input`, `--text-main`, `--text-muted` y `--border`; en tema oscuro hereda las variables oscuras.
- **Dock compacto:** altura base de 58 px, ancho máximo de 680 px y solo 78 px de safe area inferior. La última fila de tarjetas termina encima del dock sin reservar la franja vacía de la versión anterior.
- **Launchpad más denso:** hasta 4 columnas en tablet landscape/ancho amplio, tarjetas de 104 px y separación menor; sigue bajando a 3/2/1 columnas según el ancho físico disponible.
- **Fluidez:** entrada de página, aparición de dock, aparición escalonada de tarjetas, press feedback, sheet con easing y transición breve entre rutas internas. Se respeta `prefers-reduced-motion`.
- **Cache bust:** `tablet_runtime.js` y `tablet_experience.css` usan la revisión `20260827-tablet9`.

### Validación v9

- `pytest`: 26 pruebas de contrato tablet/release pasaron.
- `scripts/client_ui_audit.py`: OK.
- `scripts/static_release_audit.py`: OK (118 Jinja templates, 256 endpoints, 147 assets, 15 JS files).
- `scripts/ui_consistency_audit.py`: OK.
- `py_compile` de `app.py`, `dashboard.py` y `launchpad.py`: OK.
- `node --check static/js/tablet_runtime.js`: OK.

## V10 — estado tablet global y persistente entre módulos

Se corrigió el fallo donde el launchpad aparecía en tablet pero una tarjeta podía abrir el módulo con el shell de escritorio.

Cambios principales:

- `session['tablet_mode']` es el estado autoritativo mientras la sesión está activa.
- Se añadió la cookie canónica `orbis_ui_mode=tablet|desktop`; el antiguo `orbis_tablet_mode=0` ya no puede apagar una sesión tablet activa por accidente.
- Cada `url_for()` interno hereda `_tablet=1` automáticamente durante el modo tablet.
- Las tarjetas del launchpad incluyen `_tablet=1` explícitamente como respaldo adicional.
- El runtime añade `_tablet=1` a navegación interna y formularios, cubriendo enlaces/acciones creados dinámicamente.
- Todas las plantillas autenticadas que cargan `app_head_assets.html` renderizan la clase `tablet-mode` directamente en `<html>` antes de ejecutar JavaScript.
- Solo `/tablet/disable` o `/exit-tablet` desactivan el perfil tablet.
- Los assets tablet usan versión de caché `20260827-tablet10`.

Resultado esperado: desde que el usuario pulsa **Modo tablet**, cualquier pantalla autenticada (Ventas, Inventario, Compras, Clientes, Caja, Reportes, etc.) se renderiza bajo el shell y los breakpoints tablet hasta que el usuario pulsa **Escritorio**.
