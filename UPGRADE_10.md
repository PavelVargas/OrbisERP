# OrbisERP — actualización reforzada

Esta versión mantiene `FISCAL_MODE=disabled` y no pretende sustituir una integración fiscal certificada.

## Cambios principales

- Cantidades e importes validados con reglas compartidas y valores finitos.
- Restricciones PostgreSQL para impedir stock negativo, líneas inválidas y pagos no positivos.
- Bloqueos transaccionales en venta, compra, ajuste, transferencia y ubicación.
- Claves de idempotencia persistentes para evitar solicitudes duplicadas.
- Aislamiento de divisas y entidades operativas por empresa.
- El límite mensual cuenta únicamente ventas completadas.
- Sesiones revocables y desactivación de usuarios sin destruir su historial.
- Enlaces de recuperación de contraseña de un solo uso.
- Auditoría automática de escrituras y bitácora protegida contra modificación o eliminación.
- Comprobantes de pago nuevos guardados fuera de la carpeta pública.
- Protección contra fórmulas peligrosas en CSV.
- Health check que detecta migraciones pendientes.
- Flujo de calidad automático con PostgreSQL y pruebas.
- Centro visual de integridad con diagnóstico de inventario, ventas, pagos, transferencias y procesos.
- Auditoría general filtrable y exportable, enriquecida con endpoint e identificador de solicitud.
- Panel de estado técnico para PostgreSQL, migraciones, almacenamiento, correo y último respaldo.
- Registro de procesos de importación con resultado, avance y detalle de errores.
- Sesiones activas revocables por dispositivo y códigos de recuperación 2FA de un solo uso.
- Documentos con carpetas, navegación tipo Drive, previsualización, búsqueda, movimiento y renombrado.
- Foto de perfil persistente reutilizada en navegación, CRM y auditoría.
- Reglas de alertas extensibles y personalizadas que alimentan la bandeja de Notificaciones.
- CRM reconstruido con ficha legible, embudo, tareas, actividad y manejo robusto de estados.
- Modo tablet persistente en toda la navegación, con barra superior y dock táctil.

## Actualización segura

1. Realiza una copia de PostgreSQL, archivos públicos y almacenamiento privado.
2. Instala dependencias: `pip install -r requirements.txt`.
3. Ejecuta `flask --app app db upgrade`.
4. Ejecuta `flask --app app audit-integrity`.
5. Si no reporta inconsistencias, ejecuta `flask --app app validate-integrity`.
6. Ejecuta `pytest -q` con una base PostgreSQL exclusiva para pruebas.
7. Ejecuta `flask --app app check-production` y `flask --app app check-integrations`.
8. Despliega y comprueba `/operations/health/ready`.

La revisión Alembic esperada para este paquete es `a3c7d5e9f102`. Confirma el valor vigente con `python scripts/release_identity.py` y verifica que coincida con `flask --app app db current`. La primera petición autenticada posterior a esta versión exige una sesión registrada en servidor, por lo que los usuarios que ya estaban conectados deberán iniciar sesión nuevamente.

No omitas el respaldo ni ejecutes las pruebas contra la base de producción.
