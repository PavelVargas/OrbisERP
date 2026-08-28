# OrbisERP — puesta en producción

## Requisitos

- Python 3.12, PostgreSQL 15 o superior, HTTPS y un volumen persistente para `static/uploads`.
- Nunca copies `.env` al repositorio ni a un ZIP de entrega. Parte de `.env.example`, genera secretos nuevos y rota cualquier clave que haya sido compartida.
- En producción utiliza `APP_ENV=production`, `COOKIE_SECURE=1`, `AUTO_CREATE_SCHEMA=0` y una `DATABASE_URL` exclusiva.
- Mantén `FISCAL_MODE=disabled` mientras no exista una integración fiscal autorizada. Los documentos mostrarán `DOCUMENTO NO FISCAL`.

## Despliegue

1. Crea la base de datos y configura las variables.
2. Instala dependencias con `pip install -r requirements.txt`.
3. Ejecuta `flask --app app db upgrade`.
4. Ejecuta `flask --app app audit-integrity` y luego `flask --app app validate-integrity`.
5. Ejecuta `flask --app app check-production` y, para la primera instalación, `flask --app app create-superadmin`.
6. Inicia con `gunicorn --config gunicorn.conf.py app:app` o `docker compose -f docker-compose.production.yml up -d`.
7. Configura Nginx o el balanceador para HTTPS y `TRUST_PROXY=1` si reenvía `X-Forwarded-*`.
8. Verifica `/operations/health/live` y `/operations/health/ready`.
9. Ejecuta `flask --app app check-integrations` para comprobar almacenamiento y SMTP.

## Cobro mensual

El sistema mantiene pagos manuales y añade un receptor neutral de webhooks en `POST /operations/billing/webhook`. El proveedor debe enviar JSON firmado con HMAC-SHA256 en `X-Orbis-Signature` usando `BILLING_WEBHOOK_SECRET`.

Eventos admitidos: `payment.succeeded`, `payment.failed`, `subscription.activated`, `subscription.renewed` y `subscription.cancelled`. Cada evento requiere `id`, `type`, `company_id`, `provider` y `data`. En pagos exitosos, `data` admite `plan`, `amount`, `currency`, `period_start`, `period_end`, `invoice_id`, `customer_id` y `subscription_id`.

Usa `BILLING_MODE=manual` hasta contratar una pasarela. Para automatizar, configura `BILLING_MODE=webhook`, un secreto aleatorio de al menos 32 caracteres y un adaptador del proveedor que traduzca sus eventos a este contrato. Nunca presentes el modo manual como cobro automático.

## Divisas

Las tasas se introducen manualmente o se consultan con `FREECURRENCY_API_KEY`. Si la API no está configurada o no responde, el sistema conserva una tasa existente pero nunca inventa una tasa predeterminada. Las monedas están aisladas por empresa.

## Tareas programadas

Ejecuta `POST /superadmin/cron/check-expirations` enviando `X-Orbis-Cron-Secret`. El valor debe coincidir con `CRON_SECRET` y tener al menos 32 caracteres. Un superadministrador autenticado también puede ejecutarlo.

## Operaciones administrativas

El Centro operativo incluye devoluciones con reintegro de stock, cuentas por cobrar, cuentas por pagar, gastos, conteos físicos y alertas. Cuando una orden de compra queda completamente recibida se genera una cuenta por pagar interna `AUTO-OC-{id}` con vencimiento sugerido a 30 días.

Los conteos físicos deben ser completados por un operador y aprobados por un usuario con `stock.count_approve`; la aprobación genera movimientos de inventario y auditoría. La verificación 2FA se activa individualmente desde **Seguridad de acceso**.

## Gobierno y soporte

- **Centro de integridad** muestra inconsistencias de stock, asignaciones por ubicación, ventas, pagos, transferencias antiguas y procesos fallidos.
- **Auditoría general** permite filtrar y exportar hasta 10,000 eventos por empresa. Cada escritura registra endpoint e identificador de solicitud para soporte.
- **Estado del sistema** comprueba base de datos, revisión Alembic, almacenamiento, SMTP y evidencia del último respaldo.
- **Procesos** conserva el resultado de cada importación CSV. La ejecución sigue siendo transaccional y en línea; para cargas mayores a 5,000 filas se requiere añadir una cola de trabajo externa.
- **Sesiones activas** permite cerrar un dispositivo o todas las demás sesiones. Al cambiar permisos, desactivar una cuenta o restablecer su contraseña, la sesión deja de ser válida.
- Los códigos de recuperación 2FA se muestran una sola vez, se guardan mediante HMAC y cada código queda invalidado al usarlo.

## Respaldos

- `docker-compose.production.yml` incluye un servicio diario de respaldo de PostgreSQL, imágenes y comprobantes privados. Copia el volumen `backups` a otra infraestructura; un volumen en el mismo servidor no protege ante pérdida total.
- El servicio web monta el volumen de respaldos en solo lectura y muestra la fecha de `.last-success`; esto prueba que el respaldo se ejecutó, no que pueda restaurarse.
- Conserva también el volumen `static/uploads`.
- Ejecuta una restauración de prueba al menos una vez al mes.
- El script de restauración exige `CONFIRM_RESTORE=RESTORE` para evitar accidentes.

## Lista de lanzamiento

- Ejecutar la suite con `pytest` usando una base PostgreSQL exclusiva de pruebas.
- Probar ventas concurrentes, recepción de compras, transferencias, cierres y permisos.
- Crear monitores para health checks, errores 5xx, espacio en disco, CPU y conexiones PostgreSQL.
- Configurar SMTP y probar recuperación de contraseña.
- Revisar las plantillas legales con un abogado y contador de República Dominicana.
- Hacer un piloto con empresas reales antes de abrir registros públicos.
- Contratar una prueba de penetración externa y documentar la corrección de hallazgos; la suite interna no sustituye esa validación independiente.
- Rotar `SECRET_KEY`, contraseña PostgreSQL, `CRON_SECRET`, credenciales SMTP y secretos de cobro antes del lanzamiento.

## Release comercial 2026.08

### Registro y verificación de correo

En producción `REQUIRE_EMAIL_VERIFICATION=1` es obligatorio. Las cuentas creadas desde el registro público no pueden iniciar sesión hasta confirmar el enlace enviado por SMTP. Las cuentas antiguas se migran como verificadas para no bloquear clientes existentes; los usuarios creados por un administrador de empresa se consideran cuentas provisionadas internamente.

El registro público está desactivado por defecto en producción (`PUBLIC_REGISTRATION=0`). Para SaaS autoservicio:

```env
PUBLIC_REGISTRATION=1
REQUIRE_EMAIL_VERIFICATION=1
TERMS_URL=https://tu-dominio/legal/terminos
PRIVACY_URL=https://tu-dominio/legal/privacidad
LEGAL_VERSION=2026-01
```

El arranque de producción rechaza registro público con URLs no HTTPS o `LEGAL_VERSION=draft`. Cada alta pública guarda `terms_accepted_at` y `legal_version`.

### Pruebas HTTP reales

El CI ya no se limita a compilar Jinja. Con `TEST_DATABASE_URL` crea una empresa/usuario/producto/cliente/venta de QA y hace requests reales contra Dashboard, Productos, Cliente 360, CRM, Ventas, Almacenes, Caja, Documentos, Alertas, Auditoría, Integridad, Estado del sistema y Perfil. También prueba el round-trip de archivar un producto con valores `Decimal` de PostgreSQL.

### Mantenimiento automatizado

Docker Compose incluye un servicio `maintenance`. Ejecuta diariamente:

- limpieza de datos efímeros;
- comprobación de PostgreSQL y revisión Alembic;
- escritura en almacenamiento privado;
- frescura del último backup;
- procesos fallidos recientes;
- cajas abiertas por más de 24 horas.

Comando manual:

```bash
flask --app app maintenance-check --strict
flask --app app maintenance-clean --retention-days 30
```

### Respaldos verificables

`backup_postgres.sh` ahora escribe primero archivos temporales, valida el dump con `pg_restore --list`, valida los TAR, genera SHA-256 y solo entonces actualiza `.last-success`.

```bash
scripts/verify_backup.sh
```

Si montas almacenamiento externo y configuras `BACKUP_MIRROR_DIR`, cada backup se replica también a ese directorio. El directorio debe estar realmente en otra infraestructura para considerarse off-site.

Una vez al mes ejecuta `scripts/restore_drill.sh` contra una base **exclusiva de simulacro**. Consulta `MAINTENANCE.md`.

### Logs

Usa `LOG_JSON=1` en producción para obtener logs estructurados apropiados para un colector externo. Cada 500 conserva `request_id` y stack trace en el log. El sistema no incluye por sí solo un SaaS de monitorización; conecta stdout/stderr a la plataforma de observabilidad elegida.

### Empaquetado

Nunca distribuyas el workspace directamente. Genera un artefacto limpio:

```bash
python scripts/build_release.py --output dist/orbiserp_release.zip
```

El builder excluye `.env`, `.git`, cachés, bytecode, logs, backups, almacenamiento privado y `static/uploads` de clientes, y valida la integridad del ZIP.
