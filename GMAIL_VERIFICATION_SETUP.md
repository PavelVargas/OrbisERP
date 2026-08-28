# Verificación de correo con Gmail

OrbisERP ahora verifica las cuentas nuevas con un código de 4 dígitos enviado por correo.

## Variables requeridas

Configura estas variables en `.env` antes de registrar usuarios:

```env
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=1
MAIL_USERNAME=tu_cuenta@gmail.com
MAIL_PASSWORD=TU_APP_PASSWORD_DE_GMAIL
MAIL_DEFAULT_SENDER=tu_cuenta@gmail.com
REQUIRE_EMAIL_VERIFICATION=1
VERIFY_EMAIL_CODE_MINUTES=10
VERIFY_EMAIL_MAX_ATTEMPTS=5
```

`MAIL_PASSWORD` debe ser una credencial de aplicación de Gmail, no la contraseña normal de la cuenta.

## Actualizar PostgreSQL

Esta versión agrega estado de verificación por código al modelo `users`. Antes de iniciar la aplicación ejecuta:

```bash
source .venv/bin/activate
flask --app app db upgrade
```

Después inicia normalmente:

```bash
python app.py
```

## Flujo nuevo

1. El usuario crea su cuenta.
2. OrbisERP envía un correo HTML con un código de 4 dígitos.
3. El código vence en 10 minutos y tiene un máximo de 5 intentos.
4. Después de verificar, el usuario inicia sesión.
5. La misma cuenta crea la empresa y queda como administrador/propietario.
