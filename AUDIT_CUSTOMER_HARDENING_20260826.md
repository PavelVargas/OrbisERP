# Auditoría funcional y UX — OrbisERP 2026.08.11

Fecha de revisión: 2026-08-26

## Alcance de este pase

Este pase se enfocó en los defectos reportados durante validación de cliente: impresión térmica, órdenes de compra, modo solo lectura, Superadmin, dark mode, caja por sucursal, devoluciones, garantías, feedback de errores, edición de usuarios sin relogin, importaciones de cantidades y modo tablet/POS.

## Cambios aplicados

1. **Impresora y ticket térmico**
   - Se añadió acceso directo `Configuración > Impresora y tickets`.
   - La configuración Retail permite ancho de 40 a 112 mm, con presets 58/60/72/80 mm.
   - Se guarda método de impresión (`BROWSER`, `WEBUSB`, `ELECTRON`), nombre del dispositivo y autoimpresión.
   - Se incorporó vista previa visual dentro de Configuración.
   - El ticket al lado de Factura PDF ahora abre un preview dedicado, ajustable por ancho antes de imprimir.
   - Se agregó una migración Alembic para persistir la configuración.

2. **Órdenes de compra**
   - La creación ya no falla silenciosamente al faltar/provenir de un proveedor inválido: explica el motivo en pantalla.
   - El formulario de producto se compactó a una sola línea tipo documento/Odoo: producto, variante, UOM, cantidad, costo, ITBIS y acción.
   - Se valida server-side que la unidad de compra pertenezca a la categoría y conversiones permitidas del producto.
   - Las cantidades UNIT/serializadas permanecen enteras; productos por peso/UOM fraccionaria conservan decimales válidos.

3. **Modo solo lectura y errores**
   - Se muestra banner persistente explicando que no se guardarán altas/cambios/cobros/recepciones/eliminaciones.
   - Las operaciones bloqueadas entregan una explicación accionable en la interfaz.
   - Se añadió un modal de feedback centrado para errores/advertencias de negocio y errores de interfaz.
   - Errores HTTP 400/409/429/500 muestran una pantalla segura con referencia de incidente; los 500 no exponen trazas ni secretos.

4. **Superadmin**
   - Se rediseñó el centro maestro con navegación superior, KPIs, salud de plataforma, alertas, búsqueda, tarjetas de empresas, acciones de soporte y mejor jerarquía visual.
   - Se incorporó dark mode sin flash inicial.

5. **Dark mode**
   - El tema se aplica antes de cargar la hoja visual principal mediante `theme-preload` y lectura de `localStorage`.
   - `theme-sync.js` mantiene `html`, `body`, `data-theme` y `color-scheme` sincronizados.
   - Se bloquean animaciones/transiciones durante el primer paint para eliminar el parpadeo claro al cambiar de pantalla.

6. **Caja por sucursal**
   - Una sesión de caja queda asociada explícitamente a `branch_id` y opcionalmente `terminal_id`.
   - Apertura/cierre/arqueo calculan únicamente ventas en efectivo y gastos de esa sucursal/terminal.
   - Usuarios asignados quedan bloqueados a su sucursal; administradores pueden seleccionar una sucursal activa.
   - Abrir/cerrar caja en una sucursal no modifica las demás.
   - Se añadió migración y restricción de caja abierta por empresa + usuario + sucursal.

7. **Devoluciones**
   - El flujo comienza buscando el número de venta (`125`, `#125`, `VEN-000125`).
   - Solo se aceptan ventas completadas de la empresa actual.
   - Se calcula lo ya devuelto y el máximo restante por línea.
   - El operador elige destino físico: Disponible, Cuarentena, Dañado o No reintegrar.
   - Disponible crea entrada de stock; Cuarentena/Dañado se segregan; lotes y seriales mantienen trazabilidad.
   - La devolución queda enlazada a venta original, importe, método de reembolso y auditoría.
   - Se aclara que una reversión bancaria/tarjeta externa debe confirmarse en el proveedor de pagos correspondiente.

8. **Garantías**
   - Abrir una garantía NO devuelve automáticamente el producto al stock vendible.
   - Un serial reclamado pasa a estado `WARRANTY`.
   - Reparación: el original sigue asociado a la venta, sin entrada de stock.
   - Reemplazo: se descuenta exactamente una unidad/serial disponible del almacén, se registra movimiento OUT, el serial nuevo se vincula a la venta y el original queda `SCRAPPED`.
   - Rechazo/cierre: no crean entrada automática de stock.
   - Si el producto regresa físicamente, debe procesarse por Devoluciones para definir el destino real del inventario.

9. **Usuarios en tiempo real**
   - Nombre, rol, permisos, almacén, sucursal y terminal se leen desde DB en cada petición.
   - El contexto de sesión se sincroniza en la siguiente petición, sin obligar a relogin.
   - Cambio de contraseña sigue siendo un límite de seguridad y revoca sesiones mediante `session_version`.

10. **Importaciones y cantidades**
    - `UNIT` y serializados rechazan cantidades fraccionarias como `1.5`.
    - Solo productos por peso o UOM explícitamente fraccionarias aceptan decimales.
    - Valores con más precisión de la admitida se rechazan, no se redondean silenciosamente.
    - Importaciones de LOT/SERIAL deben entrar con stock 0 y registrar trazabilidad después.

11. **Tablet / POS**
    - `tablet_runtime.js` usa `visualViewport` para altura real, orientación y detección de teclado virtual.
    - Mantiene inputs enfocados visibles cuando aparece el teclado.
    - POS tablet usa layout de pantalla completa, targets táctiles más grandes y carrito fijo/scroll independiente.
    - Se eliminaron offsets de sidebar del flujo tablet y se añadió topbar/dock consistente en pantallas no-POS.

## Validación ejecutada

- `python3 -m compileall`: OK.
- Sintaxis Node de JS modificados: OK.
- `scripts/static_release_audit.py`: OK.
- `scripts/ui_consistency_audit.py`: OK.
- `scripts/client_ui_audit.py`: OK.
- `scripts/transfer_scanner_release_audit.py`: OK.
- 118 plantillas Jinja parseadas.
- 256 endpoints detectados.
- 1,162 referencias `url_for` verificadas.
- 139 assets estáticos verificados.
- 27 migraciones Alembic; una raíz y un único head `a3c7d5e9f102`.
- 15 archivos JavaScript validados con Node.
- 74 pruebas offline/de contrato ejecutables en este entorno: OK.
- Pruebas HTTP/PostgreSQL dependientes del stack completo quedan para staging porque el contenedor de auditoría no dispone de Flask-SQLAlchemy/PostgreSQL.

## Requisito de despliegue

Esta versión añade migración de base de datos. Antes de arrancar la nueva release en el entorno del cliente ejecutar:

```bash
flask --app app db upgrade
```

El arranque está configurado para rechazar un esquema viejo en lugar de operar parcialmente.

## Nota de certificación

La release queda sin defectos reproducibles dentro de los controles estáticos, contratos offline y validaciones de código disponibles en este entorno. La certificación final de producción debe incluir smoke/E2E autenticado contra una copia de staging con PostgreSQL, impresora física objetivo y tablet real del cliente.
