# Auditoría verificada — OrbisERP 2026.08.12

Fecha de revisión: 2026-08-27

## Incidente confirmado

El error reproducido en `POST /sales/add/<product_id>` no provenía de PostgreSQL ni del navegador. Una línea `SaleItem` nueva se construía con claves foráneas, pero el cálculo de precio consultaba `item.product` antes de que SQLAlchemy hubiera hecho `flush`. En esa ventana la relación podía ser `None`, por lo que `resolve_sale_price()` intentaba leer `product.price` y generaba un `AttributeError`/HTTP 500.

## Corrección funcional

- La línea nueva asigna relaciones y claves foráneas (`sale`, `product`, `variant`, `warehouse`) antes de tarificar.
- Una línea existente refresca relaciones, UOM y factor de conversión antes de recalcular.
- Producto, tenant, estado, variante, almacén, cantidad y UOM se validan dentro de la transacción, no solo en el catálogo del navegador.
- Si falla precio, disponibilidad, reserva o seriales, se restaura el estado previo de la línea y de la lista de precios; la ruta hace rollback y devuelve un error de negocio detallado con referencia.
- `resolve_sale_price()` ya no admite producto ausente, cross-tenant, archivado/desactivado, variante ajena ni un precio negativo.
- Cambiar cliente mantiene `sale.client`, `client_id`, `price_list` y `price_list_id` coherentes en la misma petición. Carrito y catálogo se actualizan por AJAX.
- Aplicar/quitar promociones mantiene relación y FK coherentes para que el descuento se calcule inmediatamente.

## UX/UI verificada

- Cards del POS con jerarquía más clara, controles táctiles explícitos y acción “Agregar” visible.
- El cuerpo de una card no dispara altas accidentales y usa cursor neutro.
- Menú con secciones colapsables, estado activo reforzado e iconos SVG locales para no depender visualmente del CDN.
- Dark mode inicializado antes del primer stylesheet y assets versionados para evitar caché vieja/destellos.
- Tablet landscape sin overflow horizontal; botón de quitar con track de 44 px.
- Tablet portrait con carrito tipo drawer, overlay, apertura/cierre y contenido dentro del viewport.
- Errores de negocio del POS se presentan en popup central; no se usan `alert()` nativos.

## Controles ejecutados

### Suite offline y contratos

- 139 tests recopilados.
- 131 aprobados.
- 2 omitidos porque exigen `TEST_DATABASE_URL` PostgreSQL explícita.
- 6 deseleccionados porque requieren el runtime Flask/PostgreSQL completo de staging.

### Auditorías de release

- Python `compileall`: OK.
- Jinja: 118 plantillas parseadas.
- Endpoints: 256 detectados.
- `url_for`: 1,171 referencias comprobadas.
- Assets estáticos: 141 referencias comprobadas.
- Alembic: 27 revisiones, una raíz y un único head `a3c7d5e9f102`.
- JavaScript: 15 archivos comprobados con Node.
- Auditoría estática, consistencia UI, dark/tablet/legacy, transferencias/escáner y POS: OK.

### Chromium visual/interactivo

Escenarios: desktop light 1512×900, desktop dark 1512×900, tablet landscape 1180×820 y tablet portrait dark 820×1180.

Verificado:

- sin overflow horizontal visible;
- seis cards renderizadas en todos los escenarios;
- contraste de superficies distinto y coherente entre light/dark;
- controles “Agregar” de 40 px en desktop y 46–48 px en tablet;
- agregar producto actualiza el carrito sin recarga;
- cambiar cliente recalcula precios sin recarga;
- quitar producto actualiza el carrito;
- un error 409 muestra popup detallado;
- drawer tablet abre dentro del viewport, activa overlay y cierra correctamente.

## Validación de entrega

El ZIP se genera con `scripts/build_release.py` y se valida con `scripts/verify_release.py`. Excluye `.env`, `.git`, entornos virtuales, caches, bases locales, logs, storage y uploads de clientes.

## Límite de certificación

Este entorno no incluye Flask/Flask-SQLAlchemy/psycopg ni una base PostgreSQL de staging, por lo que no se declara “cero bugs absolutos”. Antes de producción se debe ejecutar la suite HTTP/E2E del repositorio con `TEST_DATABASE_URL`, datos representativos, tablet real e impresora térmica real. La entrega sí queda verificada en sintaxis, contratos, relaciones críticas del POS, UI estática, Chromium offline y empaquetado seguro.
