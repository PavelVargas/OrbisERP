# OrbisERP — puesta en producción

## Requisitos

- Python 3.12, PostgreSQL 15 o superior, HTTPS y un volumen persistente para `static/uploads`.
- Nunca copies `.env` al repositorio. Parte de `.env.example` y genera una `SECRET_KEY` aleatoria de 32 bytes o más.
- En producción utiliza `APP_ENV=production`, `COOKIE_SECURE=1`, `AUTO_CREATE_SCHEMA=0` y una `DATABASE_URL` exclusiva.
- Mantén `FISCAL_MODE=disabled` mientras no exista una integración fiscal autorizada. Los documentos mostrarán `DOCUMENTO NO FISCAL`.

## Despliegue

1. Crea la base de datos y configura las variables.
2. Instala dependencias con `pip install -r requirements.txt`.
3. Ejecuta `flask --app app db upgrade`.
4. Ejecuta `flask --app app check-production` y, para la primera instalación, `flask --app app create-superadmin`.
5. Inicia con `gunicorn --config gunicorn.conf.py app:app` o `docker compose -f docker-compose.production.yml up -d`.
6. Configura Nginx o el balanceador para HTTPS y `TRUST_PROXY=1` si reenvía `X-Forwarded-*`.
7. Verifica `/operations/health/live` y `/operations/health/ready`.

## Cobro mensual

El sistema mantiene pagos manuales y añade un receptor neutral de webhooks en `POST /operations/billing/webhook`. El proveedor debe enviar JSON firmado con HMAC-SHA256 en `X-Orbis-Signature` usando `BILLING_WEBHOOK_SECRET`.

Eventos admitidos: `payment.succeeded`, `payment.failed`, `subscription.activated`, `subscription.renewed` y `subscription.cancelled`. Cada evento requiere `id`, `type`, `company_id`, `provider` y `data`. En pagos exitosos, `data` admite `plan`, `amount`, `currency`, `period_start`, `period_end`, `invoice_id`, `customer_id` y `subscription_id`.

La integración concreta con una pasarela solo requiere un adaptador que traduzca sus webhooks a este contrato. Las credenciales reales nunca deben incluirse en el código.

## Operaciones administrativas

El Centro operativo incluye devoluciones con reintegro de stock, cuentas por cobrar, cuentas por pagar, gastos, conteos físicos y alertas. Cuando una orden de compra queda completamente recibida se genera una cuenta por pagar interna `AUTO-OC-{id}` con vencimiento sugerido a 30 días.

Los conteos físicos deben ser completados por un operador y aprobados por un usuario con `stock.count_approve`; la aprobación genera movimientos de inventario y auditoría. La verificación 2FA se activa individualmente desde **Seguridad de acceso**.

## Respaldos

- Programa `scripts/backup_postgres.sh` diariamente y copia los archivos a otra infraestructura.
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
