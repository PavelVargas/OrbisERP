# OrbisERP · Ajustes finales solicitados · 2026-08-29

Esta entrega parte de `solucion2.zip` y mantiene el resto del diseño POLISHED sin cambios innecesarios.

## 1. CRM

- Sustituida la capa visual residual por `static/css/crm_polished.css` como autoridad exclusiva del módulo.
- Reorganizados cartera, ficha de cliente, KPIs, embudo, tareas e historial con una composición master-detail más limpia.
- Estados Lead / Negociación / Ganado / Perdido usan colores semánticos y discretos.
- Conservados todos los IDs, `data-*` y hooks usados por `static/js/crm/crm.js`.
- Responsive y modo oscuro incluidos.

## 2. Búsqueda Ctrl+K

- El buscador del sidebar queda dedicado a filtrar el menú.
- Ctrl/Cmd+K abre una paleta global centrada y legible.
- Incluye Productos, Clientes, Proveedores, Ventas y Compras.
- Navegación por teclado: flechas, Enter y Escape.
- Renderizado de resultados mediante DOM seguro (`textContent`) y consultas con debounce/abort.

## 3. Aviso de documento no fiscal

- El aviso de detalle de venta incluye `No volver a mostrar`.
- La preferencia se persiste en `localStorage` con la clave `orbis-hide-non-fiscal-sale-notice`.
- No se elimina la información fiscal de facturas o documentos generados; solo se permite ocultar el aviso repetitivo de la interfaz.

## 4. PDF de facturas

- Eliminada la dependencia operativa de wkhtmltopdf/pdfkit en la ruta de exportación.
- Nuevo generador interno `services/sales_pdf.py` basado en ReportLab.
- Soporta logo local, datos de empresa/cliente, múltiples páginas, detalle de líneas, moneda, totales y notas.
- La ruta sigue respetando la visibilidad/tenant de la venta y devuelve el PDF inline.
- PDF de prueba multipágina generado, renderizado e inspeccionado correctamente.

## 5. POS

- Nueva composición `POS Gallery v15`, enfocada en catálogo visual.
- Imagen del producto ampliada y convertida en el elemento dominante de cada tarjeta.
- Eliminado el azul/morado dominante del POS; base neutra con naranja únicamente para acción/foco.
- Chips y metadatos reducidos para evitar ruido.
- Precio, disponibilidad, UOM/cantidad y CTA mantienen jerarquía operativa.
- Panel de pedido y dark mode alineados con la misma dirección visual.
- Hooks y flujo de venta permanecen intactos.

## 6. Retail · aplicar unidad de medida a todos

- Nueva acción en `Retail > Unidades y variantes`: `Aplicar a todos los productos`.
- Permite elegir una UOM activa y aplicarla como unidad de venta al catálogo activo.
- Productos sin unidad base reciben la seleccionada como base y venta; también como compra si estaba vacía.
- Productos con unidad base solo se actualizan cuando la categoría de medida es compatible.
- Conversiones existentes se conservan y se habilitan para venta cuando corresponda.
- Productos incompatibles se omiten de forma segura y se informa el resultado.
- Acción protegida por el permiso `retail.settings`.

## Validación realizada

- Python `compileall`: OK para los archivos modificados y auditoría estática del proyecto.
- Jinja: 118 plantillas activas verificadas por la auditoría estática.
- Endpoints detectados: 257.
- Referencias `url_for`: 1,233.
- Assets: 205 referencias verificadas.
- Alembic: 27 revisiones verificadas.
- JavaScript: `left.js` y `crm.js` pasan `node --check`.
- CSS modificado parseado sin errores.
- `scripts/static_release_audit.py`: OK.
- `scripts/client_ui_audit.py`: OK.
- Contratos visual / tablet / retail / CSP / checkout seleccionados: 21/21.

La suite HTTP completa del backend depende del runtime Flask/DB configurado para el entorno final y no se sustituye por estas comprobaciones estáticas/contractuales.
