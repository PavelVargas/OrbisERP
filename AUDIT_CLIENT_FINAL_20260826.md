# Auditoría final para entrega a cliente — OrbisERP

Fecha: 2026-08-26
Release: 2026.08.10
Alembic head: f9b2d8e4a713

## Alcance de esta segunda revisión

Se realizó una revisión adicional enfocada en consistencia visual, modo oscuro, modo tablet, plantillas heredadas, seguridad de renderizado en cliente, navegación, responsive y controles de release. La revisión evita modificar la lógica sensible de POS/recepción/impresión salvo cuando existía un defecto verificable.

## Problemas corregidos

### 1. Modo tablet incompleto / runtime no garantizado
- Se aseguró la carga global de `static/js/tablet_runtime.js` en el shell autenticado.
- El runtime usa `visualViewport` para responder a teclado virtual y cambios reales del viewport.
- Se sincronizan orientación landscape/portrait y variables CSS de alto/ancho útil.
- Se evita heredar el estado de sidebar colapsado en sesiones tablet.
- Se añaden reglas para que dock inferior, formularios, tablas y vistas legacy no queden tapados o fuera de pantalla.
- El dock se oculta cuando el teclado virtual ocupa la pantalla para no bloquear controles.

### 2. Dark mode inconsistente entre plantillas modernas y legacy
- Se consolidó el runtime de tema mediante `theme-sync.js`.
- El launchpad usa el mismo runtime canónico mediante `public-theme-toggle.js`.
- Se añadió `static/css/app_final.css` como capa final de compatibilidad para superficies, formularios, tablas, modales y textos de pantallas autenticadas heredadas.
- Se preservan deliberadamente vistas de impresión/PDF y páginas públicas para no contaminarlas con estilos del shell interno.

### 3. Estética inconsistente entre plantillas
- Las vistas modernas usan `workspace/base.html`; las vistas legacy que todavía requieren estructura propia reciben ahora las mismas variables, superficies, foco, controles y comportamiento responsive mediante la capa final compartida.
- Se homogeneizaron alturas táctiles mínimas, estados focus-visible, fondos, bordes, inputs y tablas en modo oscuro/tablet.
- Se evitó una migración masiva de POS/compras/transferencias a una plantilla nueva para reducir riesgo funcional.

### 4. Búsqueda global: interpolación insegura
- `static/js/left.js` ahora escapa URL e icono antes de insertarlos en el HTML de resultados, además del título/subtítulo que ya estaban protegidos.

### 5. Compras: preview de producto mediante `innerHTML`
- Se eliminó la interpolación directa de la URL de imagen dentro de `innerHTML`.
- La imagen se crea ahora mediante nodos DOM (`document.createElement`) y se asigna con `img.src`.

### 6. Enlaces que abren una nueva pestaña
- Todos los enlaces `target="_blank"` detectados incluyen ahora `rel="noopener"` para evitar acceso innecesario a `window.opener`.

### 7. Falta de gate específico para estas regresiones
- Se creó `scripts/client_ui_audit.py` sin dependencias externas.
- Valida tema canónico, runtime tablet, visual viewport/teclado, compatibilidad legacy, seguridad de pestañas externas y escape de resultados de búsqueda.
- Se integró en `scripts/certify_release.sh` junto a los otros gates del proyecto.

## Validaciones ejecutadas

- `static_release_audit.py`: OK
  - Python compileall: OK
  - Jinja: 118 plantillas parseadas
  - 256 endpoints detectados
  - 1138 referencias `url_for` comprobadas
  - 132 referencias de assets comprobadas
  - Alembic: 26 revisiones, una raíz y un único head
  - 13 archivos JavaScript comprobados con Node
- `ui_consistency_audit.py`: OK
- `client_ui_audit.py`: OK
- `transfer_scanner_release_audit.py`: OK
- 65 pruebas offline seleccionadas: OK
- Certificación parcial del release: OK
- Verificación del ZIP: OK, sin `.env`, `.git`, cachés, logs, backups ni datos runtime.

## Limitación de certificación

Este entorno no dispone de Flask ni de una base PostgreSQL de pruebas configurada y tampoco puede descargar las dependencias faltantes. Por ello no se ejecutaron aquí los tests HTTP/DB ni un recorrido E2E autenticado contra una instancia real. El ZIP queda sin defectos reproducibles en todos los gates disponibles, pero una garantía literal de “cero bugs” requiere obligatoriamente staging con PostgreSQL, migraciones aplicadas, datos representativos y pruebas de navegador sobre los flujos críticos.

## Gate recomendado antes de producción

En staging, configurar `TEST_DATABASE_URL` con una base PostgreSQL desechable y ejecutar:

```sh
sh scripts/certify_release.sh
```

Luego validar manualmente al menos: login/2FA, venta completa, cobro/caja, compra y recepción, transferencia y escáner, CRUD de producto/cliente/proveedor, permisos por rol, reportes, modo oscuro y tablet en portrait/landscape.
