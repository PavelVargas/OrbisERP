# Revisión técnica de OrbisERP

## Endurecimiento comercial · 19/08/2026

- Eliminados del entregable `.env`, SQLite y logs locales; añadidas exclusiones preventivas.
- Límites de autenticación persistentes en PostgreSQL y nueva migración de seguridad.
- Cron de vencimientos protegido por superadministrador o secreto de infraestructura.
- Divisas aisladas por empresa, clave de proveedor externa y soporte de tasa manual sin valores inventados.
- Diagnóstico CLI de SMTP y almacenamiento, más respaldo automático de PostgreSQL e imágenes en Docker.
- Cobro declarado explícitamente como manual o webhook; producción valida secretos, correo, cookies y migraciones.
- Ampliada la suite con higiene del paquete, permisos, cron, reglas monetarias y esquema PostgreSQL.

## Ajuste CRM y orden de compra · 19/08/2026

- Corregido el conflicto CSS que mantenía visible el estado vacío del CRM después de seleccionar un cliente.
- Añadidos estados explícitos de carga, error y reintento, selección inicial y URL persistente por cliente.
- Reforzada la carga AJAX para sesión, caché y respuestas concurrentes.
- Rediseñada la orden de compra con progreso operativo, controles más legibles, tabla comercial y resumen final adaptable.
- Reconstruido el listado de compras con indicadores, búsqueda, filtros compactos, totales y estados operativos.
- Añadida una confirmación visual del producto seleccionado y progreso de recepción por línea en el detalle.
- Reestructurada nuevamente la orden interna como espacio de trabajo: catálogo y condiciones separados, jerarquía más clara y cierre fiscal al final.
- Versionada la hoja visual de la orden para impedir que el navegador reutilice CSS anterior y reforzados estados, foco y acabados.
- Movida la hoja estructural al `head` para garantizar su carga antes del renderizado en todos los navegadores.
- Completadas las reglas de layout faltantes del progreso superior, columnas de captura y cierre inferior de la orden.

## Centro de mando comercial

- Tercera revisión visual: se redujo el patrón de “una tarjeta para todo” y se convirtió el dashboard en una composición continua por bandas y espacios de trabajo.
- Las cuatro métricas superiores ahora viven en una sola banda, con divisores y jerarquía interna en lugar de cuatro cajas independientes.
- Ventas recientes, productos, pagos, finanzas y compras se agrupan en superficies compartidas para reducir ruido visual.
- Unificada la identidad naranja mediante `--primary`: menú lateral, botones, indicadores y gráficas ahora utilizan exactamente la misma gama.
- Segunda revisión visual orientada al uso comercial diario: se eliminó el bloque oscuro protagonista y se equilibraron ventas, accesos rápidos, pendientes y actividad.
- Tipografía más cómoda, tarjetas claras, densidad moderada y naranja dosificado para trabajar durante períodos largos sin fatiga visual.
- Centro de informes reconstruido sin depender de Tailwind CDN, evitando que la pantalla aparezca completamente sin estilos cuando ese recurso no carga.
- Informes, inventario, cierres de caja y exportaciones ahora comparten la identidad visual del resto del sistema.
- Corregida la serie del gráfico de informes, que inicializaba siete ceros adicionales antes de agregar los siete días reales.
- Dashboard ejecutivo reconstruido con una jerarquía visual clara y una tarjeta protagonista para ventas netas.
- Selector real de períodos de 7, 30 y 90 días, calculado con consultas agrupadas para evitar una consulta por fecha.
- Indicadores de ventas del día, ticket promedio, resultado operativo, margen, cartera, compromisos e inventario.
- Resultado y margen basados en ventas netas, costo de los productos vendidos, devoluciones y gastos registrados.
- Banda de prioridades para existencias bajas, transferencias, pagos vencidos, ventas pendientes y devoluciones.
- Tablas compactas de actividad, ranking de productos con imágenes, mezcla de cobros y órdenes de compra.
- Panel adaptable a escritorio, tablet y móvil, con estados vacíos y modo oscuro uniforme en negro suave y naranja.
- Datos financieros, compras, inventario y alertas respetan los permisos efectivos de cada usuario.
- Ventas, devoluciones, cobros y gráficos de vendedores no administradores se limitan a sus propias operaciones.
- Gráficos externos sin lógica de negocio incrustada, formato multimoneda y animaciones compatibles con accesibilidad.

## Rediseño comercial unificado

- Nuevo sistema visual suave y consistente para todas las pantallas internas.
- Navegación reorganizada según el trabajo real: ventas, inventario, compras, control y configuración.
- Acción “Nueva venta” destacada para reducir pasos en la operación diaria.
- Buscador del menú con atajo `Ctrl+K`.
- Sidebar reconstruido como componente HTML válido, accesible y adaptable a móvil.
- Una sola tipografía, escala de colores, espaciado, bordes, sombras y estados.
- Tablas, formularios, tarjetas, filtros, botones y etiquetas comparten el mismo patrón.
- Formularios en dos columnas en escritorio y una columna en móvil.
- Tablas protegidas con desplazamiento horizontal en pantallas pequeñas.
- Botones de formularios bloquean envíos dobles accidentales.
- Login, registro y recuperación alineados con la nueva identidad comercial.
- Modo oscuro rediseñado con contraste moderado y sin negro puro.

## Catálogo y formularios de producto

- Foto opcional para productos y servicios, con vista previa antes de guardar.
- Validación real del archivo y conversión automática a WebP optimizado.
- Imágenes visibles en catálogo, ficha del producto y selector de punto de venta.
- Posibilidad de cambiar o quitar la imagen posteriormente.
- Costo unitario y precio de venta obligatorios y mayores que cero, validados en interfaz y servidor.
- Creación rápida de categorías dentro del formulario mediante una ventana modal.
- La categoría nueva queda seleccionada sin recargar la página ni borrar los campos ya escritos.
- Prevención de categorías duplicadas aunque cambien mayúsculas y minúsculas.
- Nuevos filtros del catálogo por tipo y orden por fecha, nombre o precio.
- Estado vacío informativo cuando no existen productos o ningún filtro coincide.
- Ficha del producto reorganizada con foto, SKU, categoría, tipo y descripción reales.
- Eliminada la gráfica de rendimiento ficticia que podía interpretarse como información real.
- Grids refinados para catálogo, almacenes, usuarios, empresas, formularios y móvil.
- Conexión local directa a PostgreSQL: base `db_inventario`, usuario `postgres` y contraseña configurada para el entorno local.
- Eliminados el fallback, las ramas de compatibilidad y la configuración operativa de otros motores.
- Compatibilidad automática con instalaciones PostgreSQL existentes: agrega `products.image_path` al iniciar si aún no existe.
- Corrección automática de instalaciones antiguas: amplía `users.password` de 150 a 255 caracteres antes del primer inicio de sesión seguro.
- El inicio de sesión revierte correctamente la transacción y muestra una explicación si PostgreSQL rechaza una actualización del hash.
- Los identificadores de categoría enviados por los formularios se convierten y validan como enteros antes de consultar PostgreSQL.
- Las acciones del CRM validan los identificadores JSON para evitar comparaciones incompatibles entre texto y enteros.
- Actualizadas las consultas globales visibles en el registro para SQLAlchemy 2 y el cálculo UTC sin APIs obsoletas.
- Carga de imágenes reforzada: acepta cualquier formato raster que Pillow pueda verificar, normaliza orientación y convierte a WebP.
- Los formularios de producto ahora muestran claramente los errores de validación en lugar de regresar silenciosamente a la misma pantalla.
- Si PostgreSQL rechaza una edición, se revierte la transacción y se elimina la copia de imagen que no llegó a asociarse.
- Corregido el conflicto global que eliminaba el padding de las tarjetas del dashboard.
- La consola de mando ahora usa márgenes exteriores, separación vertical y padding interno consistentes en escritorio, tableta y móvil.
- Ubicaciones jerárquicas por almacén: zonas, pasillos, tramos y niveles con código único.
- Etiquetas Code128 descargables y resolución instantánea de ubicaciones mediante escáner.
- Traslados entre almacenes o entre dos tramos del mismo almacén, conservando el stock agregado y el stock físico por ubicación.
- Distribución controlada de existencias a ubicaciones sin permitir asignar más unidades que las disponibles.
- Reserva de cantidades pendientes y bloqueos de fila al recibir para reducir sobreasignaciones y dobles recepciones.
- Filtros avanzados de ventas por vendedor, cliente, producto/SKU, fecha, estado, pago y rangos de total.
- Filtros de productos por categoría, tipo, disponibilidad, fecha de creación, precio y orden.
- Sistema global de animaciones fluidas para entradas, tarjetas, controles y acciones, respetando `prefers-reduced-motion`.

## Corregido en esta entrega

- Contraseñas protegidas con hash y migración automática de claves antiguas al iniciar sesión.
- Eliminadas las credenciales fijas del superadministrador; la conexión PostgreSQL local usa los datos solicitados para `db_inventario`.
- El superadministrador solo se crea mediante `SUPERADMIN_EMAIL` y `SUPERADMIN_PASSWORD`.
- Modo debug desactivado por defecto y cookies reforzadas.
- Autenticación central para las rutas privadas, control de operaciones administrativas y modo solo lectura real.
- La API de usuarios ya no expone usuarios de otras empresas.
- Restablecimiento de contraseñas limitado a la empresa activa y respuestas anti-enumeración.
- Acciones destructivas de compras y divisas cambiadas de GET a POST.
- Validación de origen para escrituras, límite de archivos y cabeceras HTTP de seguridad.
- SKU único por empresa, no global; se incluye migración Alembic.
- Relación SQLAlchemy duplicada eliminada.
- Hojas de estilo inexistentes corregidas.
- Radios exagerados de 51 px, reglas globales con `!important` y alineación rota del dashboard corregidos.
- Favicon desacoplado de un archivo subido por un cliente.
- Dependencia duplicada de PostgreSQL corregida.

## Puesta en marcha

1. Crear un entorno virtual e instalar `requirements.txt`.
2. En local, PostgreSQL queda listo para `db_inventario`. Configurar `SECRET_KEY`, `SUPERADMIN_EMAIL` y `SUPERADMIN_PASSWORD`; `DATABASE_URL` solo se necesita para usar otro servidor PostgreSQL.
3. Ejecutar `flask --app app db upgrade` antes de iniciar la versión actualizada.
4. En producción, mantener `COOKIE_SECURE=1` y no activar `FLASK_DEBUG`.

## Riesgos que requieren una fase posterior

- No existe una suite de pruebas de negocio; conviene cubrir ventas, recepción parcial, transferencias y caja.
- Los archivos subidos viven en disco local. En despliegues efímeros deben moverse a almacenamiento persistente.
- Varias pantallas conservan CSS propio y dependencias externas; la base visual ya está estabilizada, pero una unificación total requiere revisión visual pantalla por pantalla con datos reales.
- El cron de vencimientos debe protegerse con autenticación de infraestructura antes de exponerse públicamente.
# Pulido de inventario por ubicación, escáner y ventas

- Los filtros de productos y ventas ahora viven en un botón compacto junto al buscador.
- El escáner es un módulo visible en el menú y en el Centro de Transferencias.
- La recepción por escáner exige validar la etiqueta de la sububicación destino antes de contar productos.
- Cada tramo muestra su stock propio por producto, transferencias pendientes y un kardex detallado.
- Las asignaciones y transferencias guardan fecha, referencia, cantidad, saldo posterior y responsable.
- La tabla de ventas fue reequilibrada, simplificada y adaptada a escritorio, tableta y móvil.
# Control granular de usuarios y permisos

- Matriz de 58 permisos en la edición de usuarios, organizada en diez áreas operativas.
- Perfiles rápidos: Mínimo, Vendedor, Almacén, Auditor y Supervisor.
- Ocultación automática de módulos y acciones no autorizadas en el menú y las vistas.
- Protección central de 100 endpoints Flask y APIs; escribir la URL manualmente no omite el control.
- Administradores con acceso total y usuarios operativos configurables individualmente.
- Auditoría de cambios de permisos con responsable, fecha, IP, permisos añadidos y retirados.
- Migración PostgreSQL y actualización automática de `users.permissions` para instalaciones existentes.

# Identidad naranja, ventas y transferencias simplificadas

- Portada pública reconstruida con una identidad comercial naranja, jerarquía clara y contenido alineado con las funciones reales del sistema.
- Eliminado el amarillo como color principal; navegación, accesos, estados de énfasis y pantallas heredadas usan la paleta naranja unificada.
- Listado de ventas reorganizado con resumen operativo, buscador principal y filtros avanzados dentro de un botón compacto.
- Punto de venta equilibrado para escritorio, tableta y móvil, con catálogo visual, carrito legible y cierre de venta consistente.
- Corregido el JavaScript del cierre de ventas para usuarios sin permiso de completar ventas.
- Creación de transferencias reducida a dos controles visibles: Origen y Destino.
- Cada selector combina almacén y ubicación física; los campos internos compatibles con el backend se completan automáticamente.
- Eliminados de la transferencia los selectores duplicados y el panel de escaneo improvisado; el escáner sigue disponible como módulo independiente.
- Validación de stock, diferencia entre origen y destino, búsqueda de productos y trazabilidad por ubicación conservadas.

# CRM, categorías, existencias, proveedores y tablet

- CRM operativo con indicadores, búsqueda, filtros por etapa, creación y finalización de tareas, notas tipificadas y cambios de embudo validados.
- Corregido el acceso cruzado a tareas de otras empresas y añadidas validaciones de autenticación, contenido y estados.
- Categorías reorganizadas con buscador, conteo real de productos, estados vacíos y prevención de nombres duplicados.
- Existencias reconstruidas con indicadores, imágenes, vista en cuadrícula o tabla, filtros compactos, distribución por almacén e historial accesible.
- Eliminadas las consultas repetitivas por producto y almacén en existencias mediante una carga consolidada.
- Creación rápida de proveedores dentro de la nueva orden de compra, mediante popup y selección automática sin perder el formulario.
- Diseño específico para tablet en orientación vertical y horizontal, con paneles adaptables, controles táctiles y contenido sin desbordamientos.

# Modo oscuro unificado

- Todo el sistema usa ahora el mismo carbón neutro de la portada (`#0e0f11`) y superficies grises, sin fondos verdes.
- Unificadas las variables de páginas, tarjetas, campos, bordes, textos y estados hover de módulos nuevos y heredados.
- Sidebar, login, registro, ventas, CRM, categorías, existencias, transferencias y trazabilidad comparten la misma identidad oscura.
- El naranja permanece como único acento de marca; verde y rojo se reservan para estados semánticos de éxito y error.

# Órdenes de compra: corrección y rediseño

- Corregido el error `invalid literal for int() with base 10: '1.00'`: cantidades como `1.00` se aceptan si representan unidades enteras.
- Las cantidades fraccionarias, cero, negativas, infinitas o mal formadas se rechazan con mensajes claros sin provocar errores 500.
- El costo unitario se valida como importe positivo, finito y con dos decimales.
- El producto se comprueba contra el catálogo activo de la empresa antes de añadirlo.
- La recepción parcial utiliza la misma validación segura y no permite recibir más unidades que las pendientes.
- Totales de unidades e importes se recalculan mediante una consulta consolidada después de agregar o quitar líneas.
- Eliminados los formularios HTML anidados de la plantilla anterior.
- Vista de creación de la orden reconstruida con estética naranja, modo oscuro neutro, imágenes, resumen lateral y popup de recepción.
- Adaptación específica para escritorio, tablet y móvil sin depender de Tailwind en esta pantalla.

# Transferencias internas entre tramos y gavetas

- Corregida la validación que impedía transferir entre puntos diferentes del mismo almacén.
- Se permite stock general → ubicación, ubicación → stock general, ubicación → ubicación y padre → sububicación.
- Solo se rechaza una transferencia cuando almacén y ubicación de origen coinciden exactamente con almacén y ubicación de destino.
- Los movimientos internos conservan sin cambios el total agregado del almacén y reasignan únicamente el stock físico por ubicación.
- El mensaje de confirmación diferencia una recepción entre almacenes de una reasignación interna entre tramos.

# Bandeja de transferencias pendientes

- El Centro de Transferencias muestra únicamente operaciones en estado `PENDING`.
- Al validar o recibir una transferencia, desaparece inmediatamente de la bandeja y de los contadores por almacén.
- La transferencia recibida no se elimina: permanece registrada para auditoría, kardex y trazabilidad.
- Los almacenes sin pendientes muestran un estado vacío claro en lugar de una tabla en blanco.

# Compras: ITBIS, proveedores y orden compacta

- Impuestos configurables por empresa y por línea de compra, con ITBIS exento, 18% no incluido y 18% incluido creados automáticamente.
- Creación de nuevos tipos de ITBIS desde la misma orden y opción para aplicar un impuesto a todas sus líneas.
- Cálculo fiscal consistente: base imponible, impuesto y total general, incluyendo la extracción correcta cuando el ITBIS ya está incluido en el costo.
- Cambio del proveedor asignado y edición rápida de nombre, correo y teléfono sin salir de la orden.
- Acciones Guardar orden y Descartar ubicadas junto al número y estado de la orden.
- Editor de productos reequilibrado con producto, cantidad, costo e impuesto en una sola estructura adaptable.
- Tabla de productos con imágenes, impuestos por línea, encabezado fijo, altura máxima, scroll y contadores de productos y unidades.
- Resumen fiscal movido al final de la pantalla para mantener primero el flujo de captura y revisión.
- Migración Alembic y actualización automática compatibles con la base PostgreSQL local existente.

# Preparación comercial y operación mensual

- Eliminadas las credenciales PostgreSQL y de correo incrustadas; configuración central mediante `.env` con validación estricta en producción.
- Gunicorn, Docker, health checks, migración de lanzamiento y configuración de proxy/HTTPS listos para despliegue.
- Protección CSRF automática para formularios y `fetch`, cookies seguras, HSTS, CSP, bloqueo de intentos, política de contraseñas y logout por POST.
- Auditoría estructurada de operaciones mutables con identificador de solicitud y páginas de error seguras para soporte.
- Suscripciones con facturas, períodos, mora, gracia, cancelación, reactivación y webhooks HMAC idempotentes, manteniendo también el pago manual existente.
- Asistente de configuración inicial para empresa y almacén principal.
- Centro de importación/exportación CSV aislado por empresa para productos, inventario inicial, clientes y proveedores.
- Almacenamiento persistente mediante volumen, validación real de imágenes/PDF y aplicación de cuota del plan a fotos de productos.
- Bloqueo transaccional de la empresa al finalizar ventas para impedir exceder el límite mensual mediante ventas concurrentes.
- Scripts seguros de respaldo y restauración PostgreSQL con retención configurable.
- Suite inicial de pruebas, verificación de 79 plantillas y documentación de producción, seguridad, webhooks y preparación legal.
## Corrección de migraciones PostgreSQL existentes (2026-08-18)

- Las migraciones de imágenes, ubicaciones, trazabilidad y permisos ahora son idempotentes: si una tabla, columna, índice o relación ya existe, Alembic no intenta duplicarla.
- `flask --app app db upgrade` ya no ejecuta la autorreparación local mientras Alembic importa la aplicación.
- Esto resuelve `psycopg.errors.DuplicateColumn: products.image_path` sin borrar ni reiniciar `db_inventario`.
## Suite operativa integral y Dashboard V2 (2026-08-18)

- Devoluciones parciales o completas con cantidades controladas, reembolso, auditoría y reintegro opcional al inventario.
- Cuentas por cobrar con abonos parciales, métodos, referencias y actualización transaccional del balance.
- Cuentas por pagar con vencimientos, documentos únicos por empresa y pagos parciales o completos.
- Registro de gastos por categoría, proveedor, método, fecha y referencia.
- Conteos físicos por almacén o sububicación, diferencias y aprobación separada que genera kardex.
- Centro de notificaciones para stock bajo y cuentas vencidas.
- Autenticación 2FA TOTP compatible con aplicaciones autenticadoras estándar, sin servicio externo.
- Stock mínimo y máximo configurable en productos.
- Modo fiscal desactivado y aviso `DOCUMENTO NO FISCAL` en la vista y el PDF de ventas.
- Centro operativo responsive y nuevos permisos independientes para cada función.
- Dashboard V2 con ventas netas, devoluciones, gastos, cuentas por cobrar/pagar, valor del inventario, alertas, métodos de pago, compras y consumo del plan usando datos reales.
- Migración PostgreSQL idempotente `c8f2a91d640e` y cobertura de rutas nuevas.
## Compatibilidad del ejecutor de pruebas (2026-08-18)

- La raíz del proyecto se agrega explícitamente al `PYTHONPATH` de pytest.
- `pytest -q` y `python -m pytest -q` ahora importan `security` y `models` de la misma manera.
# Mejora comercial de módulos — 18/08/2026

- Gestión de personal con vista alternable entre lista y tarjetas, búsqueda y contador.
- Directorio de clientes rediseñado con filtros, acceso directo a CRM y permisos correctos.
- CRM estabilizado: selección automática, acceso por `?client=`, cálculos monetarios y fechas defensivas.
- Cuadre de caja renovado con conteo asistido por denominaciones y validación decimal segura.
- Importación/exportación con zona de arrastre, plantillas CSV y mensajes de validación claros.
- Escáner alineado con la estética comercial y entrada manual compatible con tablet.
- Historial mensual creado desde cero con métricas, filtros y exportación.
- Corregido el 400 al agregar productos mediante formularios POS creados por JavaScript.
# Renovación de módulos operativos — 19/08/2026

- Configuración de empresa alineada con la estética comercial, vista previa del logo y validaciones de datos.
- Modo tablet reconstruido con tarjetas táctiles, búsqueda y módulos filtrados por permisos.
- CRM adaptado al alto de la pantalla: la ficha completa queda visible y solo desplazan las listas internas.
- Kardex renovado con métricas, búsqueda, filtros avanzados, almacén y rango de fechas seguro.
- Proveedores con indicadores de compras, filtros, búsqueda y eliminación protegida cuando existen relaciones.
- Notificaciones explicadas, clasificadas y accionables; cada aviso se marca al abrir y los problemas resueltos cierran alertas pendientes.
# Refuerzo de integridad y operación 10/10 — 19/08/2026

- Cantidades, importes e identificadores críticos ahora usan validadores compartidos que rechazan cero, negativos, fracciones indebidas, NaN e infinitos.
- Ventas, compras, ajustes, ubicaciones y transferencias utilizan bloqueos de fila en operaciones concurrentes.
- PostgreSQL impide nuevas filas con stock negativo, cantidades no positivas, pagos inválidos o estados desconocidos.
- Nueva migración `2a6e8c4b1d70` con sesiones revocables, usuarios desactivables, consolidación segura de stock duplicado e idempotencia persistente.
- Cada formulario y `fetch` de escritura incorpora una clave de operación; repetir la misma solicitud devuelve conflicto sin duplicar el movimiento.
- Las tasas de cambio de login, caja y venta quedan aisladas por empresa.
- Los límites mensuales consideran solo ventas completadas.
- Los enlaces de recuperación quedan invalidados después del primer cambio de contraseña.
- Las escrituras exitosas se auditan automáticamente y PostgreSQL protege la bitácora contra edición o eliminación.
- Los comprobantes de pago nuevos se guardan fuera de `static` y solo el superadministrador puede abrirlos.
- Exportaciones CSV neutralizan fórmulas de hojas de cálculo.
- Readiness comprueba conexión, almacenamiento y revisión Alembic.
- Se añadieron comandos `audit-integrity` y `validate-integrity`, respaldos de almacenamiento privado y CI con PostgreSQL.
- Suite ampliada a 44 pruebas recolectadas; 42 pasan localmente y 2 de PostgreSQL se reservan para el entorno de integración.

# Gobierno operativo, sesiones y recuperación — 19/08/2026

- Nuevo Centro de integridad visual con comprobaciones en vivo y acceso directo a transferencias pendientes.
- Auditoría general por empresa con filtros, paginación, exportación CSV segura, endpoint e identificador de solicitud.
- Estado del sistema con latencia PostgreSQL, revisión Alembic, pool, disco, SMTP, versión y último respaldo confirmado.
- Historial paginado de procesos de importación, filas procesadas y errores de validación.
- Registro de sesiones en servidor, revocación individual o masiva y cierre automático cuando cambia la cuenta.
- Códigos de recuperación 2FA de un solo uso almacenados mediante HMAC, con regeneración protegida por contraseña y TOTP.
- Migración idempotente `3b7f9d5c2e81`, navegación y permisos granulares para todas las vistas nuevas.
- Las validaciones que necesitan terceros —restauración real, pentest y piloto comercial— permanecen declaradas como controles externos y no se presentan como realizadas.
- Verificación final: 50 pruebas recolectadas, 48 aprobadas localmente y 2 de integración PostgreSQL reservadas para CI o una base de pruebas real.
- Corregido el enlace de sesiones activas del menú y añadida una prueba global que detecta endpoints literales inexistentes en las plantillas.
