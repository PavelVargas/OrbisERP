# Política técnica de seguridad de OrbisERP

OrbisERP aplica defensa en profundidad en autenticación, autorización, sesión, datos, archivos, infraestructura y operación. Esta política describe los controles técnicos incluidos en el release comercial; no sustituye una política legal, un análisis de riesgos del cliente ni requisitos regulatorios de su jurisdicción.

## Identidad y acceso

- Las contraseñas se almacenan con hashes de Werkzeug y las credenciales legacy se migran al autenticarse.
- La política de contraseña exige al menos 12 caracteres; las passphrases largas son compatibles.
- TOTP de seis dígitos, códigos de recuperación, sesiones revocables y `session_version` reducen el riesgo de secuestro de sesión.
- Los registros públicos nuevos requieren verificación de correo cuando `REQUIRE_EMAIL_VERIFICATION=1`; los usuarios existentes se migran como verificados para evitar bloqueos durante el upgrade.
- Cada módulo privado exige sesión válida, empresa activa y permiso RBAC de endpoint. Las comprobaciones de empresa se realizan también en backend, no solo ocultando controles en HTML.
- Los vendedores con almacén asignado quedan ligados a ese almacén para operaciones de inventario y venta; no se confía en un `warehouse_id` enviado por el navegador.

## Sesión, formularios y navegador

- Cookies `HttpOnly`, `SameSite=Lax` y `Secure` obligatorio en producción.
- HSTS, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy` y CSP con nonce para bloques `script`/`style`.
- Solicitudes mutables requieren CSRF y validaciones de origen. Las operaciones sensibles pueden utilizar claves de idempotencia persistidas en PostgreSQL.
- Login, registro, recuperación y reenvío de verificación usan limitación persistente compartida entre workers Gunicorn.
- Los enlaces enviados por correo se construyen desde `PUBLIC_BASE_URL`; en producción debe ser HTTPS para no confiar en un `Host` controlado por el cliente.

## Datos, multitenancy e integridad

- Las entidades comerciales se filtran por `company_id`, y las operaciones sensibles validan de nuevo la pertenencia de las entidades antes de mutarlas.
- PostgreSQL aporta constraints, transacciones y bloqueos `FOR UPDATE` en flujos donde concurrencia e inventario lo requieren.
- Dinero y tasas de cambio se normalizan con `Decimal`; no se mezcla aritmética financiera `Decimal/float` en los flujos corregidos.
- Alembic es la autoridad de migraciones de producción. `flask --app app check-production` comprueba el head esperado antes del arranque comercial.
- La auditoría registra actor, empresa, IP, resultado y request ID. La integridad de auditoría se puede comprobar mediante `audit-integrity`/`validate-integrity`.

## Archivos privados

- Los documentos privados se guardan fuera del árbol público bajo `STORAGE_ROOT`.
- Las extensiones permitidas se validan junto con la firma/contenido real de PDF, imágenes y documentos Office; no se confía únicamente en `Content-Type` del navegador.
- Los nombres de carpetas/archivos rechazan caracteres de control y separadores de ruta; renombrar un documento no permite alterar su extensión.
- Avatares e imágenes de producto se decodifican y re-encodan antes de persistirse.

## Webhooks y observabilidad

- Los webhooks de facturación verifican firma HMAC y son idempotentes.
- El cron de infraestructura exige autenticación administrativa o secreto HMAC.
- Los errores 5xx reciben un `request_id` que se muestra al usuario y se escribe en logs estructurados.
- `ERROR_WEBHOOK_URL` permite enviar incidentes a un receptor externo; en producción debe usar HTTPS y una clave HMAC de al menos 32 caracteres. El payload omite formularios, JSON de entrada y contraseñas.
- Los endpoints de salud exponen estado y versión de release, no secretos.

## Producción e infraestructura

- El contenedor web corre como usuario no privilegiado, con filesystem de aplicación de solo lectura, `no-new-privileges` y capabilities Linux eliminadas.
- El despliegue oficial presupone un único reverse proxy de confianza (`TRUST_PROXY=1`) que termina TLS; no habilites esta opción si la aplicación es accesible directamente desde clientes no confiables.
- SMTP cifrado mediante TLS es obligatorio en la configuración comercial validada.
- CI usa PostgreSQL real, auditoría de dependencias, tests HTTP y smoke tests con navegador Playwright.
- Los backups se generan de forma atómica, se validan con `pg_restore --list` y producen manifest SHA-256. Para resiliencia real deben replicarse fuera del servidor y probarse con restore drills periódicos.

## Alcance fiscal y legal

- El release comercial fuerza `FISCAL_MODE=disabled`. Los documentos generados por OrbisERP son no fiscales salvo que en el futuro se integre y certifique el mecanismo fiscal exigido por la jurisdicción del cliente.
- Si se habilita registro público en producción, OrbisERP exige URLs HTTPS de Términos y Privacidad y una `LEGAL_VERSION` publicada, y registra la aceptación. El contenido legal debe ser revisado por profesionales competentes antes del lanzamiento.

## Respuesta a incidentes

Conserva el código de soporte mostrado al usuario y busca el mismo `request_id` en los logs o en el receptor de incidentes. Nunca solicites contraseñas, códigos TOTP ni códigos de recuperación al cliente. Ante un incidente confirmado: revoca sesiones afectadas, rota secretos comprometidos, preserva auditoría, verifica integridad y restaura desde un respaldo validado cuando sea necesario.
