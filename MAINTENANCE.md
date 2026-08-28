# OrbisERP — mantenimiento operativo

Esta guía cubre mantenimiento técnico. No sustituye la política de soporte acordada con cada cliente.

## Diario

- Mantener activos los health checks `/operations/health/live` y `/operations/health/ready`.
- Ejecutar `flask --app app maintenance-check --strict`.
- Verificar el último respaldo con `scripts/verify_backup.sh`.
- Revisar errores 5xx por `request_id` en logs y **Estado del sistema**.
- Revisar procesos fallidos y cajas abiertas por más de 24 horas.

Con Docker Compose, el servicio `maintenance` ejecuta limpieza no destructiva y comprobaciones una vez al día. El servicio `backup` realiza el respaldo separado.

## Semanal

- Revisar `governance/system`, `governance/integrity` y `governance/processes`.
- Confirmar espacio libre en PostgreSQL, almacenamiento privado, uploads y backups.
- Revisar usuarios/sesiones activas y desactivar accesos que ya no correspondan.
- Instalar actualizaciones en staging antes de producción.

## Mensual

1. Copiar el respaldo a infraestructura distinta del servidor principal.
2. Ejecutar un **simulacro real de restauración** en una base exclusiva:

```bash
CONFIRM_RESTORE_DRILL=RESTORE_TEST_ONLY \
RESTORE_TEST_DATABASE_URL='postgresql+psycopg://.../orbiserp_restore_test' \
scripts/restore_drill.sh backups/orbiserp_YYYYMMDDTHHMMSSZ.dump
```

3. Abrir la aplicación contra la restauración y ejecutar `pytest`/smoke tests en staging.
4. Rotar credenciales cuando corresponda y comprobar expiración de certificados TLS.

## Limpieza segura

```bash
flask --app app maintenance-clean --retention-days 30
```

Solo elimina datos efímeros de rate limiting, claves de idempotencia antiguas y sesiones ya revocadas. **No elimina ventas, auditoría, inventario, pagos ni documentos comerciales.**

## Antes de actualizar

```bash
scripts/backup_postgres.sh
scripts/verify_backup.sh
flask --app app check-production
flask --app app audit-integrity
```

Después instala el release, ejecuta `flask --app app db upgrade`, `flask --app app validate-integrity` y verifica los health checks.

## Política de incidentes

Cada error 500 incluye un `request_id`. Conserva ese identificador al abrir un incidente. En producción usa `LOG_JSON=1` y envía stdout/stderr del contenedor a un colector central (Loki, ELK, CloudWatch, Datadog, etc.). El software registra la excepción; la retención y alertas externas dependen de tu infraestructura.

## Release y rollback

Nunca actualices producción directamente desde una carpeta de desarrollo. Genera el artefacto con:

```bash
python scripts/build_release.py --output dist/orbiserp_release.zip
python scripts/verify_release.py dist/orbiserp_release.zip
```

Antes de desplegar conserva el release anterior y un backup verificado. Si una actualización falla, restaura primero el release anterior; si la migración modificó datos/esquema de forma incompatible, usa exclusivamente un respaldo probado o el procedimiento de downgrade que haya sido validado en staging. No improvises un `DROP COLUMN` en producción.
