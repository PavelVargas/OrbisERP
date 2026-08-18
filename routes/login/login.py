from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from models.user.user import User
from models.divisas.divisas import ExchangeRate 
from db import db
from flask_mail import Message
from sqlalchemy.exc import SQLAlchemyError
import logging

login_bp = Blueprint('login_bp', __name__)
logger = logging.getLogger(__name__)

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

        # 3. Limpiar sesión y cargar datos de identidad básica
        session.clear()
        session['user_id'] = user.id
        session['user_name'] = user.name
        session['user_role'] = user.role

        # ==========================================
        # 🔑 LÓGICA DE MONEDA PREDETERMINADA
        # ==========================================
        # 1. Obtener la moneda del usuario (Prioridad: DB -> Default DOP)
        selected_currency = user.default_currency if user.default_currency else 'DOP'
        session['selected_currency'] = selected_currency

        # 2. Buscar en ExchangeRate usando 'currency_code' (EL NOMBRE CORRECTO)
        # Cambié .filter_by(code=...) por .filter_by(currency_code=...)
        exchange = ExchangeRate.query.filter_by(currency_code=selected_currency).first()
        
        if exchange:
            session['currency_symbol'] = exchange.symbol
        else:
            # Símbolos de emergencia por si no existe en la tabla aún
            defaults = {'DOP': 'RD$', 'USD': '$', 'EUR': '€'}
            session['currency_symbol'] = defaults.get(selected_currency, '$')

        # ==========================================
        # LÓGICA DE REDIRECCIÓN POR ROL (Jerarquía)
        # ==========================================

        if user.role == 'superadmin':
            flash(f'Modo Maestro: Bienvenido {user.name}', 'success')
            return redirect(url_for('superadmin_bp.admin_dashboard'))

        if user.company_id:
            session['company_id'] = user.company_id
            session['warehouse_id'] = user.warehouse_id 
            flash(f'Sesión iniciada correctamente', 'success')
            return redirect(url_for('dashboard_bp.dashboard'))
        
        else:
            flash('Debes registrar tu empresa para continuar', 'warning')
            return redirect(url_for('company_bp.create_company'))

    # Si es GET
    return render_template('login/login.html')

@login_bp.route('/logout')
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
