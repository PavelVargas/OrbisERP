# CRM Polish · 2026-08-29

Esta revisión modifica exclusivamente la presentación del CRM y añade un hook de stylesheet final vacío al layout workspace para permitir que el CRM tenga su autoridad visual propia sin alterar el resto del ERP.

## Cambios

- El CRM deja de cargar `module_refresh.css` como su stylesheet visual de módulo.
- Nueva autoridad visual: `static/css/crm_polished.css`.
- El stylesheet del CRM se carga después de `orbis_refined.css` para evitar conflictos de especificidad con generaciones anteriores.
- Resumen comercial convertido en una banda única de métricas con divisores coherentes.
- Directorio de clientes simplificado: buscador, filtros, selección activa, avatar y estados.
- Cabecera de cliente, KPIs, embudo, tareas e historial rediseñados con menor ruido visual.
- Modo oscuro basado exclusivamente en los tokens canónicos de POLISHED.
- Responsive específico para desktop, laptop, tablet y móvil.
- Sin `rgba()`, colores alpha ni gradientes en la hoja CRM.
- IDs, `data-*`, endpoints, formularios y hooks de `crm.js` preservados.

## Validación

- `python -m compileall -q .`: OK
- `scripts/static_release_audit.py`: OK (118 plantillas)
- `scripts/ui_consistency_audit.py`: OK
- `scripts/client_ui_audit.py`: OK
- Contratos visual/tablet/retail/CSP seleccionados: 21/21
- `test_crm_state_layer_keeps_hidden_panels_hidden`: OK
- `tinycss2`: 0 errores de parseo en `crm_polished.css`
