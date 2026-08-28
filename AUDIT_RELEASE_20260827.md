# Auditoría final de entrega — OrbisERP 2026.08.13

## Objetivo

Esta iteración parte del ZIP `crud(20260827-054609).zip` y atiende tres bloqueos de presentación: finalización de ventas, coherencia visual con el menú y comportamiento real de todas las vistas autenticadas en modo tablet.

## Correcciones funcionales del POS

- La venta de mostrador ya no exige cliente para efectivo, tarjeta o transferencia. El documento queda registrado como **Consumidor final**.
- Crédito, redención de puntos y apartados continúan exigiendo un cliente válido.
- La línea de venta recibe las relaciones ORM de producto, variante, almacén y venta antes de calcular precio; esto evita que pricing reciba `product=None`.
- La finalización bloquea la venta con `FOR UPDATE`, valida empresa, usuario, estado, almacenes e ítems, recalcula importes y ejecuta inventario, pagos y estado dentro de una sola transacción.
- Un error previo al commit produce rollback y un mensaje de negocio accionable. Un fallo de webhook posterior al commit se registra en logs, pero no presenta una venta ya guardada como fallida.
- Repetir la petición sobre una venta ya completada es idempotente: responde con la venta existente y no vuelve a descontar stock ni registrar pagos.
- El botón **Confirmar venta** se habilita al existir líneas, incluso sin cliente. Al restaurar una página desde la caché del navegador, su estado se calcula desde el carrito vivo y no desde variables renderizadas antiguas.

## Sistema visual unificado

- El menú lateral se toma como referencia para las vistas autenticadas: grafito, naranja operativo, superficies, bordes, radios, sombras, densidad e iconografía local.
- Encabezados de módulos, formularios, controles, tablas, tarjetas, estados y acciones reciben la misma capa visual compartida.
- Se eliminaron plantillas duplicadas no utilizadas que podían reintroducir una segunda estética.
- Se corrigió el buscador de Clientes, que podía comprimirse hasta quedar del ancho de un icono por una colisión entre el CSS global y el select de etapa.
- Los iconos críticos del menú y del contenido tienen fallback SVG local y no dependen completamente de un CDN.

## Tablet universal

- El modo tablet no se limita al POS: la clase de aplicación se activa en todas las vistas autenticadas.
- El runtime utiliza `visualViewport`, orientación, safe areas y detección del teclado virtual.
- Los controles alcanzan geometría táctil, los inputs evitan zoom involuntario, las tablas reciben wrappers desplazables y las rejillas se reducen a una columna en portrait.
- La barra superior y el dock se mantienen visibles en módulos generales. En POS se usa una cabecera específica y el pedido funciona como drawer en portrait.
- Se verificaron landscape y portrait en Clientes, Productos y POS, en light y dark mode.

## Evidencia ejecutada

- 145 pruebas offline/de contrato: **aprobadas**.
- 6 pruebas deseleccionadas: requieren importar el runtime Flask no disponible en este runner.
- Python `compileall`: **OK**.
- 118 plantillas Jinja: **OK**.
- 256 endpoints y 1,168 referencias `url_for`: **OK**.
- 141 referencias de assets: **OK**.
- 27 migraciones Alembic, una raíz y un único head `a3c7d5e9f102`: **OK**.
- 81 archivos CSS analizados y 14 archivos JavaScript comprobados por sintaxis: **OK**.
- Auditoría estática, UI, dark/tablet/legacy, POS y transferencias/escáner: **OK**.
- 11 escenarios Chromium: **OK**, sin errores de consola/página ni overflow horizontal visible.

La evidencia detallada del navegador está en `FINAL_VISUAL_VALIDATION_20260827.json`; el resumen estructurado está en `VALIDATION_REPORT.json`.

## Límites de certificación

No existe una afirmación técnicamente honesta de “cero errores absolutos” sin ejecutar el paquete contra PostgreSQL, el runtime Flask, los datos representativos del cliente, una tablet física y la impresora real. Esta entrega sí queda sin fallos reproducibles en todos los controles ejecutables en este entorno. Antes de producción deben ejecutarse `flask --app app db upgrade`, la suite completa con `TEST_DATABASE_URL`, un ciclo venta→pago→stock→devolución en staging y el smoke de tablet/impresora física.
