from services.time_utils import utcnow
import hashlib
import hmac
import html
import logging
import secrets
from datetime import timedelta

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_mail import Message
from itsdangerous import BadSignature, SignatureExpired

from db import db
from models.user.user import User
from security import password_error

registrar_bp = Blueprint('registrar', __name__)
logger = logging.getLogger(__name__)
VERIFY_SALT = 'email-verification-salt'


def _verification_link(user):
    """Legacy signed link kept for backwards compatibility with old emails."""
    from app import s
    token = s.dumps({'user_id': user.id, 'email': user.email}, salt=VERIFY_SALT)
    path = url_for('registrar.verify_email', token=token)
    base = current_app.config.get('PUBLIC_BASE_URL')
    return f'{base}{path}' if base else url_for('registrar.verify_email', token=token, _external=True)


def _verification_code_digest(user, code):
    secret = str(current_app.secret_key or '').encode('utf-8')
    payload = f'{user.id}:{user.email.lower()}:{code}'.encode('utf-8')
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def _issue_verification_code(user):
    code = f'{secrets.randbelow(10000):04d}'
    user.email_verification_code_hash = _verification_code_digest(user, code)
    user.email_verification_code_expires_at = utcnow() + timedelta(
        minutes=int(current_app.config.get('VERIFY_EMAIL_CODE_MINUTES', 10))
    )
    user.email_verification_attempts = 0
    user.email_verification_sent_at = utcnow()
    return code


def _verification_email_html(user, code):
    safe_name = html.escape(user.name or 'Hola')
    ttl = int(current_app.config.get('VERIFY_EMAIL_CODE_MINUTES', 10))
    digits = ''.join(
        '<span style="display:inline-block;width:52px;height:64px;line-height:64px;margin:0 4px;'
        'border-radius:14px;background:#151922;border:1px solid #303846;color:#ffffff;'
        'font-size:30px;font-weight:800;text-align:center;letter-spacing:0">'
        f'{digit}</span>'
        for digit in code
    )
    return f"""<!doctype html>
<html lang="es">
<body style="margin:0;padding:0;background:#0b0d12;font-family:Arial,Helvetica,sans-serif;color:#f5f7fb">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#0b0d12;padding:36px 14px">
    <tr><td align="center">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:600px;background:#12161d;border:1px solid #242b36;border-radius:24px;overflow:hidden">
        <tr><td style="padding:34px 36px 20px;text-align:center;background:linear-gradient(135deg,#171c25,#11151c)">
          <div style="display:inline-block;padding:8px 13px;border-radius:999px;background:#2b2110;color:#f9a100;font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase">OrbisERP · Verificación</div>
          <h1 style="margin:22px 0 10px;font-size:30px;line-height:1.15;color:#ffffff">Confirma tu correo</h1>
          <p style="margin:0;color:#aeb7c4;font-size:16px;line-height:1.6">Hola {safe_name}, usa este código para activar tu cuenta y continuar con la configuración de tu empresa.</p>
        </td></tr>
        <tr><td style="padding:26px 36px 10px;text-align:center">
          <div style="margin:4px 0 22px;white-space:nowrap">{digits}</div>
          <p style="margin:0;color:#aeb7c4;font-size:14px;line-height:1.6">El código vence en <strong style="color:#ffffff">{ttl} minutos</strong>. No lo compartas con nadie.</p>
        </td></tr>
        <tr><td style="padding:24px 36px 32px">
          <div style="padding:16px 18px;border-radius:14px;background:#0d1117;border:1px solid #242b36;color:#8f9aaa;font-size:13px;line-height:1.6">Si no creaste esta cuenta, puedes ignorar este correo. OrbisERP nunca te pedirá este código por teléfono o mensajería.</div>
        </td></tr>
        <tr><td style="padding:20px 36px;border-top:1px solid #242b36;text-align:center;color:#697586;font-size:12px">© 2026 OrbisERP · Seguridad de cuenta</td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _send_verification_email(user):
    """Issue and deliver a short-lived four-digit verification code."""
    if not current_app.config.get('REQUIRE_EMAIL_VERIFICATION'):
        return True
    from app import mail

    code = _issue_verification_code(user)
    db.session.commit()

    ttl = int(current_app.config.get('VERIFY_EMAIL_CODE_MINUTES', 10))
    message = Message('Tu código de verificación · OrbisERP', recipients=[user.email])
    message.body = (
        f'Hola {user.name},\n\n'
        f'Tu código de verificación de OrbisERP es: {code}\n\n'
        f'Vence en {ttl} minutos. No compartas este código con nadie.\n'
        'Si no creaste esta cuenta, ignora este correo.'
    )
    message.html = _verification_email_html(user, code)
    try:
        mail.send(message)
        return True
    except Exception:
        logger.exception('No se pudo enviar el correo de verificacion al usuario %s', user.id)
        return False


@registrar_bp.route('/register', methods=['GET', 'POST'])
def register():
    if not current_app.config.get('PUBLIC_REGISTRATION', True):
        flash('El registro público está desactivado. Solicita acceso al administrador de OrbisERP.', 'info')
        return redirect(url_for('login_bp.login'))

    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        name = (request.form.get('name') or '').strip()
        password = request.form.get('password')
        cedula = (request.form.get('cedula') or '').strip()

        if not email or not name or not password or not cedula:
            flash('Todos los campos son obligatorios', 'error')
            return redirect(url_for('registrar.register'))
        if request.form.get('accept_terms') != '1':
            flash('Debes aceptar los Términos y reconocer la Política de Privacidad para crear la cuenta.', 'error')
            return redirect(url_for('registrar.register'))

        issue = password_error(password)
        if issue:
            flash(issue, 'error')
            return redirect(url_for('registrar.register'))
        if User.query.filter_by(email=email).first():
            flash('El email ya está registrado', 'error')
            return redirect(url_for('registrar.register'))

        if current_app.config.get('REQUIRE_EMAIL_VERIFICATION') and not (
            current_app.config.get('MAIL_USERNAME') and current_app.config.get('MAIL_PASSWORD')
        ):
            flash('Antes de crear cuentas debes configurar el correo de Gmail en el archivo .env.', 'warning')
            return redirect(url_for('registrar.register'))

        new_user = User(
            email=email,
            name=name[:150],
            password='pending-hash',
            cedula=cedula[:150],
            role='admin',
            terms_accepted_at=utcnow(),
            legal_version=current_app.config.get('LEGAL_VERSION', 'draft')[:40],
        )
        new_user.set_password(password)
        if not current_app.config.get('REQUIRE_EMAIL_VERIFICATION'):
            new_user.mark_email_verified()

        db.session.add(new_user)
        db.session.commit()

        if current_app.config.get('REQUIRE_EMAIL_VERIFICATION'):
            session.clear()
            session['verification_email'] = new_user.email
            delivered = _send_verification_email(new_user)
            if delivered:
                flash('Cuenta creada. Te enviamos un código de 4 dígitos para activarla.', 'success')
            else:
                flash('Cuenta creada, pero no pudimos enviar el correo. Revisa la configuración SMTP y usa Reenviar código.', 'warning')
            return redirect(url_for('registrar.verification_pending'))

        flash('Cuenta creada correctamente. Ahora inicia sesión para configurar tu empresa.', 'success')
        return redirect(url_for('login_bp.login'))

    return render_template(
        'registro/register.html',
        terms_url=current_app.config.get('TERMS_URL'),
        privacy_url=current_app.config.get('PRIVACY_URL'),
    )


@registrar_bp.route('/verify-email/pending', methods=['GET', 'POST'])
def verification_pending():
    email = (session.get('verification_email') or '').strip().lower()

    if request.method == 'POST':
        code = ''.join(ch for ch in (request.form.get('code') or '') if ch.isdigit())
        user = User.query.filter_by(email=email).first() if email else None
        if not user or user.email_verified:
            flash('La verificación ya no está pendiente. Inicia sesión para continuar.', 'info')
            return redirect(url_for('login_bp.login'))

        now = utcnow()
        if not user.email_verification_code_hash or not user.email_verification_code_expires_at:
            flash('Solicita un nuevo código de verificación.', 'warning')
            return redirect(url_for('registrar.verification_pending'))
        if user.email_verification_code_expires_at < now:
            flash('El código venció. Solicita uno nuevo.', 'warning')
            return redirect(url_for('registrar.verification_pending'))

        max_attempts = int(current_app.config.get('VERIFY_EMAIL_MAX_ATTEMPTS', 5))
        if int(user.email_verification_attempts or 0) >= max_attempts:
            flash('Superaste el número de intentos. Solicita un código nuevo.', 'danger')
            return redirect(url_for('registrar.verification_pending'))

        user.email_verification_attempts = int(user.email_verification_attempts or 0) + 1
        valid = len(code) == 4 and hmac.compare_digest(
            user.email_verification_code_hash,
            _verification_code_digest(user, code),
        )
        if not valid:
            db.session.commit()
            remaining = max(0, max_attempts - int(user.email_verification_attempts or 0))
            flash(f'Código incorrecto. Te quedan {remaining} intento(s).', 'danger')
            return redirect(url_for('registrar.verification_pending'))

        user.mark_email_verified()
        user.email_verification_code_hash = None
        user.email_verification_code_expires_at = None
        user.email_verification_attempts = 0
        db.session.commit()
        session.pop('verification_email', None)
        flash('Correo verificado. Inicia sesión para registrar tu empresa.', 'success')
        return redirect(url_for('login_bp.login'))

    return render_template(
        'registro/verify_email.html',
        email=email,
        code_minutes=int(current_app.config.get('VERIFY_EMAIL_CODE_MINUTES', 10)),
    )


@registrar_bp.get('/verify-email/<token>')
def verify_email(token):
    """Accept old signed verification links that may still be in inboxes."""
    from app import s

    max_age = int(current_app.config.get('VERIFY_EMAIL_MAX_AGE_HOURS', 24)) * 3600
    try:
        payload = s.loads(token, salt=VERIFY_SALT, max_age=max_age)
    except SignatureExpired:
        flash('El enlace de verificación venció. Solicita un código nuevo.', 'warning')
        return redirect(url_for('registrar.verification_pending'))
    except BadSignature:
        flash('El enlace de verificación no es válido.', 'danger')
        return redirect(url_for('registrar.verification_pending'))

    user = db.session.get(User, payload.get('user_id'))
    if not user or user.email.lower() != str(payload.get('email') or '').lower():
        flash('El enlace de verificación no corresponde a una cuenta válida.', 'danger')
        return redirect(url_for('registrar.verification_pending'))

    if not user.email_verified:
        user.mark_email_verified()
        user.email_verification_code_hash = None
        user.email_verification_code_expires_at = None
        user.email_verification_attempts = 0
        db.session.commit()
    session.pop('verification_email', None)
    flash('Correo verificado. Ya puedes iniciar sesión.', 'success')
    return redirect(url_for('login_bp.login'))


@registrar_bp.post('/verify-email/resend')
def resend_verification():
    email = (request.form.get('email') or session.get('verification_email') or '').strip().lower()
    user = User.query.filter_by(email=email).first() if email else None

    if user and not user.email_verified:
        now = utcnow()
        sent_at = user.email_verification_sent_at
        if sent_at and now - sent_at < timedelta(seconds=60):
            flash('Ya enviamos un código recientemente. Espera un minuto antes de repetir.', 'info')
            session['verification_email'] = email
            return redirect(url_for('registrar.verification_pending'))
        session['verification_email'] = email
        delivered = _send_verification_email(user)
        if delivered:
            flash('Código nuevo enviado. Revisa tu correo.', 'success')
        else:
            flash('No pudimos enviar el correo. Revisa la configuración SMTP.', 'warning')
        return redirect(url_for('registrar.verification_pending'))

    flash('Si la cuenta existe y está pendiente, enviaremos un código nuevo.', 'info')
    return redirect(url_for('registrar.verification_pending'))
