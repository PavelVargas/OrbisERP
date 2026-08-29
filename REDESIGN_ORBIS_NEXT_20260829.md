# Orbis Next — rediseño estructural 2026-08-29

Este paquete sustituye la aproximación conservadora de UI 2.0 por una migración visual estructural.

## Alcance
- 118 plantillas HTML activas migradas y parseadas sin errores Jinja.
- Nueva hoja global: `static/css/orbis_next.css`.
- Nuevo shell de escritorio: rail lateral oscuro compacto/expandible + masthead superior.
- Workspace y Backoffice migrados a canvas abierto.
- KPI cards convertidas en franjas editoriales continuas.
- Tablas convertidas a ledgers abiertos con menor ruido visual.
- Formularios e inputs sin cajas pesadas: énfasis en línea/base y foco.
- Filtros, tabs, chips y estados unificados.
- Productos cambia a vista de lista/catálogo como predeterminada.
- Módulos de Backoffice y Retail migrados de grids de tarjetas a command lists.
- Login transformado de tarjeta/split genérico a composición editorial de alto contraste.
- Home reorientado a presentación editorial/producto, con tipografía y composición más agresiva.
- Dark mode y responsive incluidos.
- Hooks funcionales, IDs, `name`, `data-*`, endpoints y formularios preservados.

## Validación ejecutada
- Jinja: 118/118 plantillas parseadas, 0 errores.
- Python compileall: OK.
- `test_visual_tablet_contract.py`: 6/6.
- `test_retail_visual_contract.py`: 3/3.
- `test_csp_attributes.py`: 3/3.
- `test_tablet_mode_v9_contract.py`: 6/6.
- `test_tablet_mode_v10_global_state.py`: 5/5.
- `test_release_20260827_checkout_tablet_unification.py`: 9/9.
- Total de contratos UI ejecutados: 32/32.

## Limitación del entorno
La suite backend completa no se pudo recolectar aquí porque faltan `flask` y `flask_sqlalchemy` en el runtime de validación. No se marca esa suite como aprobada.
