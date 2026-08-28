from services.time_utils import utcnow
from services.csp import inline_attribute_directives
import hmac
import base64
import hashlib
import logging
import json
import re
import secrets
import struct
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta

from flask import abort, current_app, g, request, session


logger = logging.getLogger(__name__)
_attempts = defaultdict(deque)
_FORM_RE = re.compile(r'(<form\b[^>]*\bmethod=["\']?post["\']?[^>]*>)', re.I)
_SCRIPT_OPEN_RE = re.compile(r'<script(?![^>]*\bnonce=)([^>]*)>', re.I)
_STYLE_OPEN_RE = re.compile(r'<style(?![^>]*\bnonce=)([^>]*)>', re.I)


def generate_totp_secret():
    """Return a Base32 secret compatible with standard authenticator apps."""
    return base64.b32encode(secrets.token_bytes(20)).decode('ascii').rstrip('=')


def hash_session_token(token):
    return hashlib.sha256((token or '').encode('utf-8')).hexdigest()


def generate_recovery_codes(count=8):
    alphabet = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'
    return [
        ''.join(secrets.choice(alphabet) for _ in range(5)) + '-' + ''.join(secrets.choice(alphabet) for _ in range(5))
        for _ in range(count)
    ]


def _recovery_hash(code):
    normalized = re.sub(r'[^A-Z0-9]', '', (code or '').upper())
    return hmac.new(current_app.secret_key.encode(), normalized.encode(), hashlib.sha256).hexdigest()


def store_recovery_codes(user, codes):
    user.totp_recovery_codes = json.dumps([_recovery_hash(code) for code in codes], separators=(',', ':'))


def consume_recovery_code(user, code):
    try:
        stored = list(json.loads(user.totp_recovery_codes or '[]'))
    except (TypeError, ValueError):
        stored = []
    supplied = _recovery_hash(code)
    for index, candidate in enumerate(stored):
        if hmac.compare_digest(candidate, supplied):
            stored.pop(index)
            user.totp_recovery_codes = json.dumps(stored, separators=(',', ':'))
            return True
    return False


def _totp_at(secret, counter):
    padded = secret.upper() + '=' * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f'{value:06d}'


def verify_totp(secret, code, valid_window=1):
    if not secret or not code or not re.fullmatch(r'\d{6}', str(code).strip()):
        return False
    counter = int(time.time()) // 30
    return any(hmac.compare_digest(_totp_at(secret, counter + delta), str(code).strip())
               for delta in range(-valid_window, valid_window + 1))


def password_error(value):
    value = value or ''
    if len(value) < 12:
        return 'La contraseña debe tener al menos 12 caracteres.'
    if len(value) > 128:
        return 'La contraseña no puede superar 128 caracteres.'
    weak = {
        'password1234', 'password12345', 'contraseña123', 'contrasena123',
        '123456789012', 'qwerty123456', 'admin12345678',
    }
    if value.strip().lower() in weak:
        return 'Elige una contraseña menos común.'
    # Longer passphrases are accepted without arbitrary composition rules.
    if len(value) < 16 and (not re.search(r'[A-Za-zÁÉÍÓÚáéíóúÑñ]', value) or not re.search(r'\d', value)):
        return 'Usa letras y números, o una frase de contraseña de 16 caracteres o más.'
    return None


def _client_key():
    # ProxyFix normaliza remote_addr cuando TRUST_PROXY está activado. Leer el
    # encabezado directamente permitiría a un cliente falsear su IP y eludir
    # el límite de intentos si la app se publica sin un proxy de confianza.
    return request.remote_addr or 'unknown'


def _rate_limited(scope, limit, window_seconds, subject=''):
    if current_app.config.get('RATE_LIMIT_STORAGE') == 'database':
        try:
            from db import db
            from models.operations import SecurityAttempt

            raw_key = f'{scope}|{_client_key()}|{str(subject).strip().lower()[:150]}'
            subject_hash = hashlib.sha256(raw_key.encode('utf-8')).hexdigest()
            cutoff = utcnow() - timedelta(seconds=window_seconds)
            count = SecurityAttempt.query.filter(
                SecurityAttempt.scope == scope,
                SecurityAttempt.subject_hash == subject_hash,
                SecurityAttempt.attempted_at >= cutoff,
            ).count()
            if count >= limit:
                return True
            db.session.add(SecurityAttempt(scope=scope, subject_hash=subject_hash))
            if secrets.randbelow(100) == 0:
                SecurityAttempt.query.filter(SecurityAttempt.attempted_at < utcnow() - timedelta(days=2)).delete()
            db.session.commit()
            return False
        except Exception:
            try:
                from db import db as database
                database.session.rollback()
            except Exception:
                pass
            logger.exception('Persistent rate limiter failed; using in-process fallback')

    now = time.monotonic()
    key = (scope, _client_key(), str(subject).strip().lower()[:150])
    bucket = _attempts[key]
    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()
    if len(bucket) >= limit:
        return True
    bucket.append(now)
    return False


def _csrf_token():
    token = session.get('_csrf_token')
    if not token:
        token = secrets.token_urlsafe(32)
        session['_csrf_token'] = token
    return token


def _consume_idempotency_key():
    key = (request.form.get('_idempotency_key') or request.headers.get('X-Idempotency-Key') or '').strip()
    if len(key) < 16 or len(key) > 100:
        abort(400, description='La operación no tiene un identificador válido. Recarga la página.')

    company_id, user_id = session.get('company_id'), session.get('user_id')
    if company_id and user_id:
        from db import db
        from models.operations import RequestIdempotency
        from sqlalchemy.exc import IntegrityError

        db.session.add(RequestIdempotency(
            company_id=company_id,
            user_id=user_id,
            request_key=key,
            endpoint=(request.endpoint or 'unknown')[:150],
        ))
        try:
            if secrets.randbelow(100) == 0:
                cutoff = utcnow() - timedelta(days=2)
                RequestIdempotency.query.filter(RequestIdempotency.created_at < cutoff).delete()
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            abort(409, description='Esta operación ya fue procesada. Recarga la página antes de repetirla.')
        return

    used = list(session.get('_used_idempotency_keys') or [])
    if key in used:
        abort(409, description='Esta operación ya fue procesada. Recarga la página antes de repetirla.')
    used.append(key)
    session['_used_idempotency_keys'] = used[-30:]


def init_security(app):
    @app.before_request
    def protect_request():
        g.request_id = request.headers.get('X-Request-ID') or secrets.token_hex(12)
        g.csp_nonce = secrets.token_urlsafe(18)
        _csrf_token()
        if request.endpoint in {'login_bp.login', 'login_bp.two_factor', 'login_bp.forgot_password', 'registrar.register', 'registrar.resend_verification'} and request.method == 'POST':
            subject = request.form.get('email', '') if request.endpoint != 'registrar.register' else ''
            if _rate_limited(request.endpoint, 10, 15 * 60, subject):
                abort(429, description='Demasiados intentos. Espera unos minutos e inténtalo de nuevo.')
        if request.method not in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            return None
        if (request.endpoint or '').startswith('api_v1.'):
            return None
        if request.endpoint in {'operations_bp.billing_webhook', 'superadmin_bp.cron_check_expirations'}:
            return None
        supplied = request.form.get('_csrf_token') or request.headers.get('X-CSRF-Token')
        if not supplied or not hmac.compare_digest(str(supplied), str(session.get('_csrf_token', ''))):
            abort(400, description='La sesión del formulario venció. Recarga la página e inténtalo nuevamente.')
        _consume_idempotency_key()
        return None

    @app.after_request
    def secure_response(response):
        response.headers['X-Request-ID'] = getattr(g, 'request_id', '')
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        response.headers.setdefault('Permissions-Policy', 'camera=(self), microphone=(), geolocation=()')
        response.headers.setdefault('Cross-Origin-Opener-Policy', 'same-origin')
        nonce = getattr(g, 'csp_nonce', '')
        style_attr_directive = "style-src-attr 'none'"
        script_attr_directive = "script-src-attr 'none'"
        if session.get('user_id') and response.content_type and response.content_type.startswith('text/html'):
            response.headers.setdefault('Cache-Control', 'no-store, private')
        if app.config.get('ENVIRONMENT') == 'production':
            response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
        if response.content_type and response.content_type.startswith('text/html') and not response.direct_passthrough:
            html = response.get_data(as_text=True)
            token = _csrf_token()
            def secure_fields(match):
                operation_key = secrets.token_urlsafe(24)
                return (
                    match.group(1)
                    + f'<input type="hidden" name="_csrf_token" value="{token}">'
                    + f'<input type="hidden" name="_idempotency_key" value="{operation_key}">'
                )
            html = _FORM_RE.sub(secure_fields, html)
            if '<head>' in html:
                html = html.replace('<head>', f'<head><meta name="csrf-token" content="{token}">', 1)
            if '</body>' in html:
                html = html.replace('</body>', '<script src="/static/js/security.js"></script></body>', 1)
            # Nonce every script/style block. Legacy attributes are authorized only
            # by hashes of the exact rendered values, never by blanket unsafe-inline.
            html = _SCRIPT_OPEN_RE.sub(lambda m: f'<script nonce="{nonce}"{m.group(1)}>', html)
            html = _STYLE_OPEN_RE.sub(lambda m: f'<style nonce="{nonce}"{m.group(1)}>', html)
            style_attr_directive, script_attr_directive = inline_attribute_directives(html)
            response.set_data(html)
        response.headers.setdefault(
            'Content-Security-Policy',
            "default-src 'self'; img-src 'self' data: blob:; object-src 'none'; "
            f"style-src 'self' 'nonce-{nonce}' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
            f"{style_attr_directive}; "
            "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net; "
            f"script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net; "
            f"{script_attr_directive}; connect-src 'self'; "
            "frame-ancestors 'self'; base-uri 'self'; form-action 'self'"
        )
        return response
