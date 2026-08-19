import hmac
import base64
import hashlib
import logging
import re
import secrets
import struct
import time
from collections import defaultdict, deque

from flask import abort, g, request, session


logger = logging.getLogger(__name__)
_attempts = defaultdict(deque)
_FORM_RE = re.compile(r'(<form\b[^>]*\bmethod=["\']?post["\']?[^>]*>)', re.I)


def generate_totp_secret():
    """Return a Base32 secret compatible with standard authenticator apps."""
    return base64.b32encode(secrets.token_bytes(20)).decode('ascii').rstrip('=')


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
    if len(value) < 10:
        return 'La contraseña debe tener al menos 10 caracteres.'
    if not re.search(r'[A-Za-zÁÉÍÓÚáéíóúÑñ]', value) or not re.search(r'\d', value):
        return 'La contraseña debe combinar letras y números.'
    return None


def _client_key():
    return request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown').split(',')[0].strip()


def _rate_limited(scope, limit, window_seconds, subject=''):
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


def init_security(app):
    @app.before_request
    def protect_request():
        g.request_id = request.headers.get('X-Request-ID') or secrets.token_hex(12)
        _csrf_token()
        if request.endpoint in {'login_bp.login', 'login_bp.two_factor', 'login_bp.forgot_password', 'registrar.register'} and request.method == 'POST':
            subject = request.form.get('email', '') if request.endpoint != 'registrar.register' else ''
            if _rate_limited(request.endpoint, 10, 15 * 60, subject):
                abort(429, description='Demasiados intentos. Espera unos minutos e inténtalo de nuevo.')
        if request.method not in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            return None
        if request.endpoint in {'operations_bp.billing_webhook'}:
            return None
        supplied = request.form.get('_csrf_token') or request.headers.get('X-CSRF-Token')
        if not supplied or not hmac.compare_digest(str(supplied), str(session.get('_csrf_token', ''))):
            abort(400, description='La sesión del formulario venció. Recarga la página e inténtalo nuevamente.')
        return None

    @app.after_request
    def secure_response(response):
        response.headers['X-Request-ID'] = getattr(g, 'request_id', '')
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        response.headers.setdefault('Permissions-Policy', 'camera=(self), microphone=(), geolocation=()')
        response.headers.setdefault('Cross-Origin-Opener-Policy', 'same-origin')
        response.headers.setdefault(
            'Content-Security-Policy',
            "default-src 'self'; img-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
            "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; connect-src 'self'; "
            "frame-ancestors 'self'; base-uri 'self'; form-action 'self'"
        )
        if session.get('user_id') and response.content_type and response.content_type.startswith('text/html'):
            response.headers.setdefault('Cache-Control', 'no-store, private')
        if app.config.get('ENVIRONMENT') == 'production':
            response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
        if response.content_type and response.content_type.startswith('text/html') and not response.direct_passthrough:
            html = response.get_data(as_text=True)
            token = _csrf_token()
            hidden = f'<input type="hidden" name="_csrf_token" value="{token}">'
            html = _FORM_RE.sub(lambda match: match.group(1) + hidden, html)
            if '<head>' in html:
                html = html.replace('<head>', f'<head><meta name="csrf-token" content="{token}">', 1)
            if '</body>' in html:
                html = html.replace('</body>', '<script src="/static/js/security.js"></script></body>', 1)
            response.set_data(html)
        return response
