# OrbisERP Serene — rediseño visual 2026-08-29

## Dirección
Esta iteración reemplaza la propuesta experimental anterior por una interfaz empresarial simple, atractiva y convencional. La navegación vuelve a un sidebar fijo y legible, con una topbar discreta. La paleta cambia a neutros claros con índigo como único acento principal.

## Cambios estructurales
- Sidebar estable de 252 px, sin rail flotante ni expansión experimental.
- Topbar compartida con búsqueda, notificaciones y perfil.
- Eliminación del masthead flotante `nx-*` de Workspace y Backoffice.
- Nuevo sistema visual `static/css/orbis_serene.css`, cargado al final para normalizar todos los módulos activos.
- Puente de tokens para impedir que CSS heredado reintroduzca el esquema naranja anterior.
- POS aislado de la topbar nueva para conservar su flujo operativo propio.
- Tablet conserva su navegación dedicada.
- Documentos PDF/térmicos/impresión quedan aislados del shell de escritorio.

## Lenguaje visual
- Fondo gris muy claro y superficies blancas.
- Índigo `#5b5bd6` para acciones y foco.
- Bordes reducidos al mínimo; predominan separación por espacio y sombras muy suaves.
- Radio estándar entre 8 y 16 px.
- Inputs sin borde visible en reposo y foco accesible.
- Tablas blancas, encabezados discretos y separadores finos.
- Métricas compactas, sin exceso de ornamentación.
- Dark mode con la misma jerarquía y semántica.

## Cobertura
- 118 plantillas HTML activas parseadas correctamente.
- 57 vistas Workspace heredan el sistema común.
- 9 vistas Backoffice heredan el sistema común.
- 29 shells autenticados directos reciben la navegación compartida.
- Vistas públicas/especiales reciben la hoja Serene de forma directa.
- Impresión/PDF conserva sus estilos dedicados.

## Contratos preservados
No se modificaron endpoints, nombres de campos, IDs funcionales, `data-*`, acciones de formularios ni hooks JavaScript necesarios para la lógica de negocio.

## Validación ejecutada
- `python scripts/static_release_audit.py`: OK
- `python scripts/ui_consistency_audit.py`: OK
- `python scripts/client_ui_audit.py`: OK
- 118/118 plantillas Jinja parseadas
- 256 endpoints / 1269 referencias `url_for` verificadas
- 246 referencias de assets verificadas
- 27 migraciones Alembic verificadas
- 15 archivos JavaScript comprobados con Node
- CSS Serene parseado con `tinycss2`: 0 errores
- Contratos visual/tablet/retail/CSP/checkout ejecutables en este entorno: 27/27

## Limitación del entorno
La suite completa de backend no puede recolectarse aquí porque el entorno actual no incluye `flask` ni `flask_sqlalchemy`. Las pruebas que dependen de esas librerías fallan en importación antes de ejecutar código de la aplicación.
