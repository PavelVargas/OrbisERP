# Auditoría técnica de entrega — OrbisERP

Fecha: 2026-08-26

## Hallazgos corregidos

1. **Paquete de entrega inseguro/no limpio**: el ZIP recibido incluía `.env`, `.git`, cachés Python/pytest, logs, backups y otros artefactos de workspace. La entrega corregida se genera con `scripts/build_release.py`, que excluye secretos, repositorio, runtime data, bases locales, caches y ZIPs anidados.
2. **Duplicados de UI heredada**: existían siete plantillas legacy que violaban el gate de consistencia visual y podían reintroducir shells/CSS duplicados: `cash/close.html`, `sales/pending.html`, `sales/quotes.html`, `sales/sales.html`, `warehouse/transfers_by_warehouse.html`, `workspace/activity.html`, `workspace/executive.html`. Se eliminaron después de verificar que no tenían referencias de rutas activas.
3. **Gate de release roto**: `scripts/static_release_audit.py` fallaba por plantillas duplicadas. Corregido; ahora pasa.
4. **Gate de UX/UI roto**: `scripts/ui_consistency_audit.py` fallaba por las mismas vistas legacy y carga inconsistente del shell. Corregido; ahora pasa.
5. **Prueba contractual desactualizada**: `tests/test_application_contract.py` exigía una implementación anterior de conversión monetaria (`raw_rate`) aunque la ruta actual usa `_product_exchange_rate()` y devuelve `Decimal`. Se actualizó el contrato para verificar la implementación decimal vigente sin degradar el código productivo.

## Validaciones ejecutadas

- `python scripts/static_release_audit.py`: OK.
- `python scripts/ui_consistency_audit.py`: OK.
- Python `compileall`: OK.
- 118 plantillas Jinja parseadas: OK.
- 256 endpoints descubiertos y 1126 referencias `url_for` verificadas: OK.
- 141 referencias de assets estáticos: OK.
- 25 migraciones Alembic con una sola raíz y un solo head: OK.
- 12 archivos JavaScript validados con `node --check`: OK.
- Pruebas offline/estáticas ejecutables en este entorno: OK; dos pruebas HTTP quedaron omitidas por requerir PostgreSQL explícito.

## Limitaciones de esta auditoría

El entorno de análisis no tuvo acceso de red para instalar las dependencias Python declaradas (Flask, Flask-SQLAlchemy, etc.). Por eso no fue posible ejecutar aquí la suite dinámica completa ni E2E contra PostgreSQL. Antes de producción deben ejecutarse los pasos de `RELEASE_CHECKLIST.md` en un entorno con dependencias y PostgreSQL de pruebas.

## Acción de seguridad recomendada

El ZIP original contenía un archivo `.env`. Si sus valores son credenciales reales o reutilizadas, deben rotarse antes de entregar o desplegar el sistema, aunque el ZIP corregido ya no los contiene.
