from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from models.user.user import User
from models.divisas.divisas import ExchangeRate 
from db import db
from flask_mail import Message
from sqlalchemy.exc import SQLAlchemyError
import logging
from security import verify_totp

login_bp = Blueprint('login_bp', __name__)
logger = logging.getLogger(__name__)


def _establish_session(user):
    session.clear()
    session.permanent = True
    session['user_id'] = user.id
    session['user_name'] = user.name
    session['user_role'] = user.role
    selected_currency = user.default_currency or 'DOP'
    session['selected_currency'] = selected_currency
    exchange = ExchangeRate.query.filter_by(currency_code=selected_currency).first()
    session['currency_symbol'] = exchange.symbol if exchange else {'DOP': 'RD$', 'USD': '$', 'EUR': '€'}.get(selected_currency, '$')
    if user.company_id:
        session['company_id'] = user.company_id
        session['warehouse_id'] = user.warehouse_id


def _login_destination(user):
    if user.role == 'superadmin':
        flash(f'Modo Maestro: Bienvenido {user.name}', 'success')
        return redirect(url_for('superadmin_bp.admin_dashboard'))
    if user.company_id:
        flash('Sesión iniciada correctamente', 'success')
        return redirect(url_for('dashboard_bp.dashboard'))
    flash('Debes registrar tu empresa para continuar', 'warning')
    return redirect(url_for('company_bp.create_company'))

@login_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password')
        
        # 1. Buscar usuario
        user = User.query.filter_by(email=email).first()
        
        # 2. Validar credenciales
        if not user or not user.check_password(password):
            flash('Correo o contraseña incorrectos', 'danger')
            return redirect(url_for('login_bp.login'))

        # Upgrade old plain-text passwords on the first successful login.
        if not user.password.startswith(('scrypt:', 'pbkdf2:')):
            try:
                user.set_password(password)
                db.session.commit()
            except SQLAlchemyError:
                # Keep the request usable and the SQLAlchemy session clean if
                # a legacy database has not yet received the schema update.
                db.session.rollback()
                logger.exception('No se pudo actualizar el hash de contraseña del usuario %s', user.id)
                flash(
                    'Pudimos validar tus datos, pero falta actualizar el esquema de seguridad. '
                    'Reinicia la aplicación e inténtalo otra vez.',
                    'warning'
                )
                return redirect(url_for('login_bp.login'))

        if user.two_factor_enabled and user.totp_secret:
            session.clear()
            session['pending_2fa_user_id'] = user.id
            session['pending_2fa_started_at'] = int(__import__('time').time())
            return redirect(url_for('login_bp.two_factor'))

        _establish_session(user)
        return _login_destination(user)

    # Si es GET
    return render_template('login/login.html')


@login_bp.route('/login/2fa', methods=['GET', 'POST'])
def two_factor():
    pending_id = session.get('pending_2fa_user_id')
    started_at = int(session.get('pending_2fa_started_at') or 0)
    if not pending_id or __import__('time').time() - started_at > 300:
        session.clear()
        flash('La verificación venció. Inicia sesión nuevamente.', 'warning')
        return redirect(url_for('login_bp.login'))
    user = db.session.get(User, pending_id)
    if not user or not user.two_factor_enabled:
        session.clear()
        return redirect(url_for('login_bp.login'))
    if request.method == 'POST':
        if not verify_totp(user.totp_secret, request.form.get('code')):
            flash('Código incorrecto o vencido.', 'danger')
            return redirect(request.url)
        _establish_session(user)
        return _login_destination(user)
    return render_template('login/two_factor.html')

@login_bp.route('/logout', methods=['POST'])
def logout():
    session.clear()
    flash('Sesión cerrada correctamente', 'info')
    return redirect(url_for('login_bp.login'))

@login_bp.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        user = User.query.filter_by(email=email).first()

        if user:
            from app import mail, s
            token = s.dumps(email, salt='password-reset-salt')
            link = url_for('users_bp.reset_with_token', token=token, _external=True)

            msg = Message("🔒 Recuperación de Acceso - OrbisERP",
                          recipients=[email])
            msg.body = f"Hola {user.name},\n\nHaz clic aquí para restablecer tu contraseña: {link}"
            
            try:
                mail.send(msg)
                flash('Te hemos enviado un correo con las instrucciones.', 'success')
            except Exception:
                # Keep the response generic so the endpoint cannot enumerate users.
                pass
        else:
            flash('Si el correo está registrado, recibirás un enlace en breve.', 'info')
        
        flash('Si el correo está registrado, recibirás un enlace en breve.', 'info')
        return redirect(url_for('login_bp.login'))

    return render_template('login/forgot_password.html')
