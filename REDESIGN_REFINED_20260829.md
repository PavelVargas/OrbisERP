# OrbisERP Refined UI · 2026-08-29

Esta revisión sustituye las generaciones UI2 / ORBIS NEXT / SERENE por una única capa visual final y predecible.

## Objetivos

- Unificar padding, márgenes, alturas, radios, controles y densidad visual.
- Eliminar transparencias y colores mezclados del sistema visual final.
- Hacer que claro y oscuro utilicen tokens explícitos y sólidos.
- Evitar que CSS de módulos históricos se cargue después del diseño final.
- Mantener intactos endpoints, IDs, nombres de campos, `data-*`, formularios y hooks JavaScript.

## Arquitectura visual

La autoridad final es `static/css/orbis_refined.css` (`20260829-refined3`). Se carga al final del `<head>` de cada documento completo, después del CSS específico del módulo.

Perfiles de pantalla:

- `orbis-app`: aplicación autenticada con sidebar/topbar.
- `orbis-public`: acceso, registro, onboarding y páginas públicas.
- `orbis-master`: administración de plataforma.
- `orbis-launchpad`: experiencia táctil/launchpad.
- `orbis-print`: facturas, recibos y reportes imprimibles.
- POS conserva su estructura operativa y recibe solo normalización cromática/controles compatible.

## Limpieza realizada

- 118 plantillas activas auditadas.
- 7 duplicados legacy sin rutas activas eliminados según las reglas de release existentes.
- 3 hojas de rediseño anteriores eliminadas: `orbis_v2.css`, `orbis_serene.css`, `orbis_next.css`.
- 0 referencias a esas generaciones anteriores.
- 0 usos de `rgba()` en plantillas o CSS.
- 135 estilos inline estáticos migrados a selectores controlados.
- Solo permanecen estilos inline dinámicos que transportan valores de runtime (porcentajes/progreso/medidas), no decisiones visuales arbitrarias.
- `orbis_refined.css` usa colores sólidos, sin gradientes ni alpha colors.

## Sistema de color

Claro:
- Canvas: `#f7f8fa`
- Superficie: `#ffffff`
- Texto: `#1d2939`
- Secundario: `#667085`
- Línea: `#e4e7ec`
- Primario: `#4f46e5`

Oscuro:
- Canvas: `#0f1218`
- Superficie: `#171b23`
- Superficie secundaria: `#1e232d`
- Texto: `#f2f4f7`
- Secundario: `#a7b0bf`
- Línea: `#2b323d`
- Primario: `#8b83ff`

Los estados éxito/advertencia/error/información tienen pares explícitos de foreground, background y border en ambos temas.

## Espaciado y geometría

Escala canónica: 4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48 px.

- Sidebar: 248 px.
- Topbar: 60 px.
- Controles: 40 px; tablet: mínimo 44 px.
- Radios: 6 / 8 / 10 / 14 / 18 px.
- Cards: borde sutil de 1 px, sin sombras decorativas.
- Tablas: padding coherente de 12×14 px y hover neutral.
- Formularios: mismo borde, foco y altura en todos los módulos.

## Validación

- Jinja: 118/118 plantillas parseadas.
- Python compileall: OK.
- Endpoints: 256 detectados.
- `url_for`: 1,228 referencias verificadas.
- Assets: 205 referencias verificadas.
- Alembic: 27 revisiones verificadas.
- JavaScript: 15 archivos verificados con Node.
- `scripts/static_release_audit.py`: OK.
- `scripts/ui_consistency_audit.py`: OK.
- `scripts/client_ui_audit.py`: OK.
- Contratos visual/tablet/retail/CSP seleccionados: 21/21.

La suite backend completa no puede ejecutarse en este entorno porque no están instalados Flask ni Flask-SQLAlchemy. No se considera certificada esa parte.
