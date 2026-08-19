# Política técnica de seguridad

- Los secretos se suministran únicamente mediante variables de entorno.
- Las contraseñas se almacenan con hashes de Werkzeug y las antiguas se migran al iniciar sesión.
- Los formularios y solicitudes JavaScript mutables requieren token CSRF.
- Login, registro y recuperación tienen limitación de intentos por dirección IP.
- Cookies HTTP-only, SameSite y Secure en producción; HSTS se activa en producción.
- Todos los módulos privados exigen autenticación, empresa activa y permisos de endpoint.
- Las acciones mutables generan líneas de auditoría con usuario, empresa, IP, resultado e identificador de solicitud.
- Los webhooks de cobro son idempotentes y verifican firma HMAC.
- Los usuarios pueden activar TOTP de seis dígitos; el desafío vence a los cinco minutos y acepta una ventana máxima de treinta segundos alrededor del reloj actual.
- Las devoluciones, abonos, pagos, gastos y aprobaciones de conteos verifican la empresa de cada entidad y se ejecutan en una transacción.

Reporte de incidentes: conserva el identificador mostrado al usuario y busca la misma referencia en `logs/orbiserp.log`. Nunca solicites contraseñas al cliente.
