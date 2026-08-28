# Corrección final del módulo escáner y transferencias — 2026-08-25

## Problema confirmado

La revisión anterior eliminó el verde global, pero dejó el área principal del escáner dependiendo del tema general. Con el ERP en modo claro, el resultado era una pantalla mezclada: menú lateral oscuro y estación de escaneo clara.

## Corrección aplicada

- La estación de escaneo usa un tema operativo oscuro propio y estable, independientemente de la preferencia clara/oscura del resto del ERP.
- Se corrigió la causa exacta de la regresión restante: `commercial.css` aplicaba fondo, controles, botones, insignias y espaciado con `!important`; el CSS del escáner ahora los sobreescribe de forma explícita y limitada a `scanner-mode-page`.
- El fondo principal es `#0c0e11`, las superficies son `#15191f` y los campos usan tonos oscuros de alto contraste.
- El naranja de OrbisERP (`#f36b21`) queda fijado como acento del módulo; ya no hereda una variable global que pudiera estar personalizada en verde.
- El buscador, el campo fraccionario, el botón de procesar, el botón final, el estado y la etiqueta SKU conservan su apariencia oscura/naranja aunque el tema global esté en claro.
- El verde se limita a estados de éxito o finalización.
- Los recursos del escáner llevan versión `20260825-dark5` para invalidar la caché del navegador.
- Transferencias y Módulo escáner no pueden quedar activos al mismo tiempo en el menú.
- El flujo distingue claramente: conduce, ubicación, producto, cantidad y confirmación.
- Se admiten SKU, identificador interno y códigos de `ProductBarcode`.
- Los productos por unidad se cuentan escaneo a escaneo.
- Los productos fraccionarios permiten registrar hasta tres decimales y exigen coincidencia con la cantidad esperada.
- El estado final ahora indica `LISTO PARA RECIBIR`, en lugar de seguir mostrando `CONTAR PRODUCTOS`.
- Se amplió a 140 ms la tolerancia para lectores Bluetooth que no envían Enter y escriben más lentamente.
- La recepción vuelve únicamente a destinos internos conocidos y no confía en `request.referrer`.
- El endpoint del escáner no usa caché y restringe el acceso al almacén de destino para usuarios no administradores.
- Productos con trazabilidad por lote o serie se bloquean en el flujo genérico para evitar pérdida de trazabilidad.

## Validación ejecutada

- Render real en Chromium a 1650×928 y 390×844.
- Tema global forzado a claro durante la prueba: la estación continuó completamente oscura.
- Color del botón principal calculado por el navegador: `rgb(243, 107, 33)`.
- Fondo calculado: `rgb(12, 14, 17)`.
- Superficie calculada: `rgb(21, 25, 31)`.
- Flujo unitario completo hasta confirmación.
- Flujo fraccionario completo con `0.375 kg` hasta confirmación.
- Sin desbordamiento horizontal en móvil.
- Auditor de escáner: OK.
- Auditor estático del release: OK.
- Auditor de consistencia visual: OK.
- 98 pruebas estáticas y de contrato aplicables: OK.

## Limitación de esta validación

No se ejecutó la suite Flask/PostgreSQL completa contra una base real porque el entorno de revisión no dispone de las dependencias Flask instaladas, no tiene acceso de red para descargarlas y no cuenta con una base PostgreSQL de pruebas. Las verificaciones de código, plantillas, assets, JavaScript y navegador descritas arriba sí se ejecutaron.
