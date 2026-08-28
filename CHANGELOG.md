# Changelog

## 2026.08.13 — checkout verificable, estética unificada y tablet universal

- Venta POS: el checkout de efectivo, tarjeta y transferencia funciona sin cliente registrado como **Consumidor final**; crédito, puntos y apartados conservan la exigencia de cliente.
- Venta POS: finalización bloqueada por fila de venta, validación de estado/empresa/usuario/almacén, transacción única para inventario y pagos, rollback ante errores e idempotencia cuando la venta ya fue completada.
- Venta POS: el fallo de una integración/webhook posterior al `commit` ya no muestra una venta exitosa como fallida ni invita a duplicarla.
- Venta POS: el estado habilitado de **Confirmar venta** se reconstruye desde el carrito vivo al volver con `pageshow`; no depende de HTML antiguo conservado por el navegador.
- Pruebas runtime offline: se ejecutan las funciones reales `_add_line`, `_payment_plan` y `finish_sale` mediante AST, cubriendo consumidor final, efectivo/tarjeta/transferencia, crédito sin cliente, carrito vacío, reintento idempotente y webhook post-commit.
- UI: todas las vistas autenticadas reciben el mismo lenguaje visual del menú — grafito, naranja operativo, radios, superficies, formularios, tablas, estados e iconografía local coherentes.
- Clientes: se corrigió una regresión de cascada que comprimía el buscador a un control del tamaño del icono; buscador y filtro mantienen geometría utilizable en escritorio y tablet.
- Tablet: shell global basado en `visualViewport`, orientación, teclado virtual, safe areas, controles táctiles, tablas desplazables y rejillas de una columna en portrait; el POS usa drawer de pedido accesible.
- POS visual: cards, buscador, cantidades, UOM, stock, carrito, pago y acciones fueron verificados en light/dark, escritorio, tablet landscape y tablet portrait.
- QA ejecutable en este entorno: **145 pruebas aprobadas**, 6 deseleccionadas por requerir Flask runtime, auditorías Python/Jinja/endpoints/assets/Alembic/JS/UI/POS/transferencias en verde y 11 escenarios Chromium sin errores de consola ni overflow visible.

## 2026.08.12 — corrección transaccional del POS y verificación visual tablet/dark

- POS: corrige el `500` al agregar un producto nuevo. La línea asigna `product`, `variant`, `warehouse` y `sale` como relaciones ORM antes de calcular el precio, sin depender de un `flush` implícito.
- POS: valida producto, empresa, estado, variante, almacén y UOM dentro de la transacción; una petición manipulada ya no puede vender con una unidad no habilitada.
- POS: una línea existente refresca sus relaciones y factor de conversión; si falla precio, stock o reserva, se restaura su estado y la lista de precios anterior antes del rollback.
- Pricing: `resolve_sale_price` rechaza producto ausente, cruzado de tenant, archivado/desactivado, variante incorrecta y precio negativo mediante errores de negocio controlados.
- Clientes/promociones: cliente, lista de precios y promoción mantienen relación ORM y clave foránea sincronizadas en la misma petición; el catálogo y el carrito se recalculan sin reiniciar la sesión ni recargar la página.
- UX: agregar, quitar y cambiar cliente usan respuesta canónica del servidor y popup detallado; el cuerpo de la tarjeta ya no actúa ni parece actuar como un botón oculto.
- Tablet: el pedido vertical abre/cierra como drawer con overlay; la línea reserva el ancho real del control táctil de eliminar y deja de desbordarse en landscape.
- Tema: el modo oscuro se aplica antes de cargar CSS y todos los assets globales usan versión de caché, reduciendo el destello al navegar y evitando estilos obsoletos.
- Navegación/POS: iconos SVG locales ampliados, estados activos más claros, cards y controles táctiles refinados en escritorio, dark mode y tablet.
- QA: 131 pruebas offline/de contrato aprobadas, 2 integraciones PostgreSQL omitidas por requerir una base explícita, auditorías Python/Jinja/JS/assets/endpoints/Alembic en verde y cuatro escenarios visuales Chromium sin overflow ni errores de consola.

## 2026.08.11 — ticket térmico, operaciones por sucursal y UX de caja/tablet

- Impresión: configuración de impresora/ticket dentro de Configuración Retail, ancho flexible de 40–112 mm, presets 58/60/72/80 mm, preview térmico real y apertura automática opcional.
- Ventas: el botón de ticket abre una vista previa limpia y ajustable antes de imprimir; Factura PDF permanece como documento independiente.
- Compras: creación de orden informa errores de proveedor en pantalla y el detalle usa una línea compacta tipo documento para producto, variante, UOM, cantidad, costo e ITBIS; se valida que la UOM sea realmente compatible con el producto.
- Caja: apertura, arqueo, ventas en efectivo y gastos quedan acotados a sucursal y, cuando existe, terminal. Una caja de una sucursal no abre/cierra las demás.
- Devoluciones: búsqueda inicial obligatoria por número de venta, cantidades remanentes, destino físico Disponible/Cuarentena/Dañado/No reintegrar, trazabilidad y movimientos enlazados a la venta.
- Garantías: una reclamación no reintegra stock automáticamente; reparación, reemplazo y rechazo tienen efectos de inventario explícitos y auditables.
- Usuarios: cambios de nombre, rol, permisos y asignación operativa se leen en la siguiente petición sin pedir relogin; solo cambios sensibles como contraseña revocan sesiones.
- UX: feedback de errores de negocio se muestra centrado y con explicación accionable; modo solo lectura muestra una advertencia persistente.
- Tema/tablet: pre-pintado de tema para eliminar el destello claro al navegar, runtime de VisualViewport/teclado y geometría táctil específica para POS tablet.
- Importaciones: cantidades de productos UNIT/serializados rechazan fracciones; solo productos/UOM configurados como fraccionarios aceptan decimales.
- Superadmin: dashboard maestro rediseñado con KPIs, salud, alertas, búsqueda y tarjetas de empresa.

- Corrección: crear producto ya no referencia `product.id` antes de inicializar el producto.
- Fotos de producto vuelven a flujo manual; importaciones CSV/XLSX no crean ni sustituyen imágenes.
- Validación de nombre/SKU alineada con PostgreSQL y Kardex registra inventario inicial.
- Se impide inventario inicial directo en productos con trazabilidad LOT/SERIAL.
- `image_url` tiene prioridad sobre `image_path`; reimportar con URL remota desacopla la foto local anterior.
## 2026.08.10 — visual coherence + POS catalog recovery


## Imágenes remotas de productos
- Productos admite `image_url` HTTPS además de `image_path`.
- El importador CSV/XLSX acepta `image_url` sin descargar ni consumir almacenamiento de la empresa.
- Catálogo, POS, ficha de producto, existencias, Kardex, compras y dashboard usan foto local primero, URL remota después y placeholder al final.
- CSP permite imágenes HTTPS externas y el importador rechaza URLs locales, privadas o con credenciales.
- Nueva migración Alembic `d7a1c4e9b206` añade `products.image_url`.

- Corrige el catálogo de Ventas/POS cuando un producto con imagen no tiene variante: ya no se desreferencia `variant.image_path` sobre `None`.
- El POS valida respuestas HTTP/JSON del catálogo, muestra estado/cantidad y ofrece reintento visible en vez de quedar vacío.
- Unifica la capa visual con `ui_unification.css`, safe areas y comportamiento consistente en escritorio/tablet.
- Corrige los contratos visuales de launchpad, workspace y sidebar en modo tablet.
- Centraliza estilos Retail 2.0 para configuración, variantes, precios, códigos, lotes/series, proveedores, garantías y calidad.
- Corrige subtítulos de Garantías y Control de calidad y elimina CSS duplicado de la ficha de producto.
- Añade gates estáticos y tests de regresión para catálogo POS y coherencia visual.
- Retira templates legacy duplicados que ya solo tenían rutas de compatibilidad/redirección.

## 2026.08.8 — schema identity single source hotfix

- Esquema: `config.py` deja de hardcodear una revisión Alembic; `EXPECTED_SCHEMA_REVISION` se deriva del único head real incluido en `migrations/versions`.
- Release: `schema_identity.py` centraliza el descubrimiento del head sin depender de Flask/SQLAlchemy.
- QA: `release_identity.py`, auditoría estática y tests verifican que el esquema esperado se derive del grafo, evitando desincronizaciones entre código y migraciones.
- Operación: una carpeta parcialmente actualizada ya no puede conservar silenciosamente un head antiguo dentro de `config.py` si el archivo de configuración pertenece a esta release.

## 2026.08.7 — release identity / deployment consistency

- QA: versión y head Alembic dejan de estar duplicados como constantes frágiles en múltiples tests.
- Release: `scripts/release_identity.py` valida `VERSION`, el único head Alembic, `EXPECTED_SCHEMA_REVISION` y cabeceras de documentación.
- Certificación: `certify_release.sh` ejecuta el chequeo de identidad antes de la auditoría estática y pruebas dinámicas.
- Mantenimiento: los tests de migraciones históricas ya no fallan cada vez que aparece un head posterior no relacionado.
- Despliegue: una carpeta mezclada entre releases se detecta de inmediato con `python scripts/release_identity.py`.

# Changelog
## 2026.08.6 — startup/RBAC/test consistency hotfix

- Fix: el rollback de arranque se ejecuta dentro de `app.app_context()`, evitando el error secundario `Working outside of application context`.
- Fix: `sales_bp.thermal_receipt` queda protegido explícitamente por `sales.print`.
- QA: la API externa `/api/v1` se clasifica correctamente como autenticación por API key/scopes, no como sesión/RBAC de usuario.
- QA: los tests de ventas validan `positive_quantity` y cantidades fraccionarias para productos por peso en vez de la antigua regla `positive_integer`.
- Release: se reafirma `EXPECTED_SCHEMA_REVISION = 9f4a2c7e1b33` y la versión comercial pasa a `2026.08.6`.


## 2026.08.5 — PostgreSQL UOM migration typing hotfix

- El seed de `units_of_measure` usa binds SQLAlchemy tipados y casts PostgreSQL explícitos para `NUMERIC`/`BOOLEAN`.
- `factor_to_reference` y `rounding` ya no se envían como `VARCHAR` bajo psycopg 3.
- Los factores semilla usan `Decimal` para evitar conversión binaria de punto flotante durante la migración.
- Se revisaron todos los parámetros enlazados de las migraciones Retail; `7a9c4e21b6d0` era el único bootstrap parametrizado afectado.
- El upgrade sigue siendo reintentable desde `6f7b2d4c9a11` después de los intentos fallidos anteriores, sin `stamp` ni borrado de datos.

## 2026.08.4 — Retail migration recovery hotfix

- La migración `7a9c4e21b6d0` ahora repara defaults SQL si Retail 2.0 fue precreado por la antigua rutina `db.create_all()`.
- El bootstrap de `company_retail_settings` inserta explícitamente todos los campos `NOT NULL`, incluidos perfiles, flags, costeo y timestamps.
- Sucursal principal, lista de precios y UOM iniciales incluyen timestamps explícitos y ya no dependen de defaults del ORM.
- El upgrade desde `6f7b2d4c9a11` es reintentable después del `NotNullViolation` sin borrar datos ni hacer `stamp`.

## 2026.08.3 — Schema startup hotfix

- El arranque ya no consulta modelos Retail 2.0 contra una base Alembic atrasada.
- Se eliminó `db.create_all()` del bootstrap runtime: Alembic vuelve a ser la única fuente de verdad del esquema.
- `python3 app.py` falla de forma explícita si la revisión no es `9f4a2c7e1b33` o faltan columnas críticas.
- El mensaje indica `flask --app app db upgrade` en lugar de continuar con una aplicación parcialmente rota.
- La creación automática del superadmin ahora hace rollback y propaga errores de base de datos.

# OrbisERP — Changelog

## 2026.08.2 — Retail Platform 2.0

### Catálogo y pricing
- Variantes y atributos configurables (talla, color, capacidad u otros).
- Múltiples códigos de barras por producto/variante.
- Unidades de medida, cantidades fraccionarias y conversiones específicas por producto.
- Listas de precios y reglas por cantidad/producto/variante/categoría.
- Relación producto-proveedor con SKU, costo, mínimo, lead time y proveedor preferido.
- Kits/combos con descuento real de componentes.

### Inventario y postventa
- Lotes, vencimientos y consumo FEFO.
- Seriales/IMEI con trazabilidad por venta y garantía.
- Devoluciones que preservan variante, UOM, lote y serial.
- Estados físicos Disponible, Cuarentena y Dañado, con Centro de Control de Calidad.
- Garantías con revisión, aprobación, reparación, reemplazo, rechazo y cierre.
- Reposición considerando unidad de compra y costeo configurable.

### POS, clientes y organización
- Sucursales y terminales POS asociadas a almacén/usuario.
- Pagos mixtos: efectivo, tarjeta, transferencia, crédito, gift card y fidelización.
- Crédito por cliente, apartados, gift cards y movimientos de puntos.
- Promociones ampliadas (porcentaje, fijo, 2x1, 3x2, segunda unidad y segmentación comercial).
- Ticket térmico 58/80 mm.

### Plataforma e integraciones
- API `/api/v1` con API keys y scopes.
- Webhooks externos firmados con HMAC y validación de destino.
- Reportes Retail: ABC, margen, valor de inventario, sucursal, terminal, vencimientos y rotación.
- Nuevo `scripts/static_release_audit.py` para certificar Python, Jinja, JS, assets, endpoints y grafo Alembic sin depender de una DB.
- Alembic head `9f4a2c7e1b33`.

## 2026.08.1 — Commercial Release Candidate

### Seguridad y acceso
- Verificación de correo para altas públicas y registro público desactivable.
- Aceptación versionada de Términos/Privacidad para autoservicio.
- Enlaces de recuperación/verificación construidos desde `PUBLIC_BASE_URL` confiable.
- Política de contraseña reforzada, rate limiting persistente, CSRF e idempotencia.
- CSP con nonces para bloques script/style y contenedor de producción endurecido.
- Validación por firma/contenido de documentos privados y MIME canónico.

### Estabilidad y QA
- Corrección de operaciones monetarias `Decimal` en Cliente 360/Productos.
- Smoke tests HTTP reales contra PostgreSQL para pantallas críticas.
- Smoke E2E con Playwright en CI para Login, Dashboard, Productos, Clientes, CRM, Ventas, Almacenes y Auditoría.
- Release builder reproducible que excluye secretos, runtime, uploads y repositorio Git.

### Operación
- Logging estructurado opcional y webhook firmado de incidentes 5xx.
- Health/readiness con versión de release.
- Comandos `maintenance-check` y `maintenance-clean`.
- Backup validado con checksums, verificación, mirror opcional y simulacro de restauración.
- Pipeline de certificación y verificación del artefacto de release.
