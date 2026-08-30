from services.time_utils import utcnow
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from models.company.company import Company, PLAN_LIMITS
from models.user.user import User
from models.productivity import SalesTax
from db import db
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
import os
import uuid
from io import BytesIO
from PIL import Image, UnidentifiedImageError
from routes.super_admin.superadmin import get_dir_size

company_bp = Blueprint('company_bp', __name__, url_prefix='/company')


# =====================================================
# FUNCIONES AUXILIARES
# =====================================================

def require_login():
    user_id = session.get('user_id')
    if not user_id:
        return None
    return User.query.get(user_id)


def upload_file(file, folder, company_id=None, *, private=False):
    """
    Versión mejorada: Si se pasa company_id, guarda en la carpeta técnica
    de la empresa para que el monitor de almacenamiento pueda contarlo.
    """
    if file and file.filename:
        filename = secure_filename(file.filename)
        extension = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        if extension not in {'png', 'jpg', 'jpeg', 'webp', 'pdf'}:
            raise ValueError('Solo se permiten imágenes PNG/JPG/WEBP o documentos PDF.')
        content = file.read()
        if not content:
            raise ValueError('El archivo está vacío.')
        if extension == 'pdf':
            if not content.startswith(b'%PDF-'):
                raise ValueError('El documento no es un PDF válido.')
        else:
            try:
                with Image.open(BytesIO(content)) as image:
                    image.verify()
            except (UnidentifiedImageError, OSError, SyntaxError) as exc:
                raise ValueError('La imagen está dañada o no es válida.') from exc
        file.stream.seek(0)
        unique_name = f"{uuid.uuid4().hex}_{filename}"

        if private:
            if not company_id:
                raise ValueError('No se pudo asociar el archivo a una empresa.')
            private_root = os.path.abspath(current_app.config['STORAGE_ROOT'])
            relative = os.path.join(f'company_{company_id}', 'receipts', unique_name)
            file_path = os.path.abspath(os.path.join(private_root, relative))
            if os.path.commonpath([private_root, file_path]) != private_root:
                raise ValueError('Ruta de almacenamiento inválida.')
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            file.save(file_path)
            return f"private:{relative.replace(os.sep, '/')}"

        # Si tenemos ID de empresa, forzamos la ruta técnica
        if company_id:
            folder = f"uploads/company_{company_id}"

        upload_dir = os.path.join(current_app.root_path, f"static/{folder}")
        os.makedirs(upload_dir, exist_ok=True)

        file_path = os.path.join(upload_dir, unique_name)
        file.save(file_path)

        return f"{folder}/{unique_name}"
    return None


def delete_file(relative_path):
    if relative_path:
        full_path = os.path.join(current_app.root_path, "static", relative_path)
        if os.path.exists(full_path):
            os.remove(full_path)


def refresh_session_user(user):
    session['user_id'] = user.id
    session['company_id'] = user.company_id
    session['user_role'] = user.role
    session['session_version'] = int(user.session_version or 1)
    session['company_name'] = user.company.name if user.company else None


# =====================================================
# CREAR EMPRESA
# =====================================================

@company_bp.route('/create', methods=['GET', 'POST'])
def create_company():
    user = require_login()
    if not user:
        return redirect(url_for('login_bp.login'))

    if user.company_id:
        existing_company = Company.query.get(user.company_id)
        if existing_company:
            session['company_id'] = existing_company.id
            session['company_name'] = existing_company.name
            session['user_role'] = user.role
            return redirect(url_for('dashboard_bp.dashboard'))
        else:
            user.company_id = None
            db.session.commit()

    if request.method == 'POST':
        business_name = (request.form.get('business_name') or '').strip()
        rnc = (request.form.get('rnc') or '').strip() or None
        company_email = (request.form.get('company_email') or '').strip().lower() or user.email
        phone = (request.form.get('phone') or '').strip() or None
        address = (request.form.get('address') or '').strip() or None

        if len(business_name) < 2:
            flash('Escribe un nombre de empresa válido.', 'danger')
            return redirect(url_for('company_bp.create_company'))
        if company_email and ('@' not in company_email or len(company_email) > 120):
            flash('Escribe un correo comercial válido.', 'danger')
            return redirect(url_for('company_bp.create_company'))
        if rnc and Company.query.filter_by(rnc=rnc).first():
            flash('Ese RNC / ID ya está asociado a otra empresa.', 'danger')
            return redirect(url_for('company_bp.create_company'))

        new_company = Company(
            name=business_name[:150],
            rnc=rnc[:20] if rnc else None,
            email=company_email[:120] if company_email else None,
            phone=phone[:20] if phone else None,
            address=address[:500] if address else None,
            expiration_date=utcnow() + timedelta(days=30)
        )

        db.session.add(new_company)
        db.session.flush()

        logo_file = request.files.get('logo')
        if logo_file and logo_file.filename:
            try:
                new_company.logo = upload_file(logo_file, 'uploads/companies/logos', company_id=new_company.id)
            except ValueError as error:
                db.session.rollback()
                flash(str(error), 'danger')
                return redirect(url_for('company_bp.create_company'))
        db.session.add(SalesTax(
            company_id=new_company.id, name='ITBIS 18%', rate=18,
            price_included=True, active=True, is_default=True,
        ))

        user.company_id = new_company.id
        user.role = 'admin'

        # Inicializar límites de almacenamiento según plan básico al crear
        limits = new_company.get_plan_limits()
        new_company.storage_limit = limits.get('storage_bytes', 524288000)

        db.session.commit()
        refresh_session_user(user)

        flash("Empresa creada correctamente", "success")
        return redirect(url_for('operations_bp.onboarding'))

    return render_template('company/create_company.html', user=user)

# =====================================================
# CONFIGURACIÓN (Actualiza almacenamiento al subir Logo)
# =====================================================

@company_bp.route('/settings', methods=['GET', 'POST'])
def settings():
    user = require_login()
    if not user:
        return redirect(url_for('login_bp.login'))

    if session.get('user_role') != 'admin':
        flash("No tienes permisos", "danger")
        return redirect(url_for('dashboard_bp.dashboard'))

    company_id = session.get('company_id')
    company = Company.query.get_or_404(company_id)

    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        email = (request.form.get('email') or '').strip().lower() or None
        if len(name) < 2:
            flash('El nombre comercial debe tener al menos 2 caracteres.', 'danger')
            return redirect(url_for('company_bp.settings'))
        if email and ('@' not in email or len(email) > 120):
            flash('Escribe un correo administrativo válido.', 'danger')
            return redirect(url_for('company_bp.settings'))
        company.name = name[:150]
        company.rnc = (request.form.get('rnc') or '').strip()[:20] or None
        company.email = email
        company.phone = (request.form.get('phone') or '').strip()[:20] or None
        company.address = (request.form.get('address') or '').strip()[:500] or None
        company.fiscal_mode = 'disabled'
        company.fiscal_disclaimer = ((request.form.get('fiscal_disclaimer') or 'DOCUMENTO NO FISCAL').strip()[:180]
                                     or 'DOCUMENTO NO FISCAL')

        logo_file = request.files.get('logo')
        if logo_file and logo_file.filename:
            try:
                new_logo = upload_file(logo_file, "uploads/companies/logos", company_id=company.id)
            except ValueError as error:
                flash(str(error), 'danger')
                return redirect(url_for('company_bp.settings'))
            delete_file(company.logo)
            company.logo = new_logo

        # 🔥 Sincronizar barra de almacenamiento después de cambios
        db.session.flush()
        company.current_storage_usage = get_dir_size(company.id)

        db.session.commit()
        session['company_name'] = company.name

        flash("Configuración actualizada y almacenamiento recalculado", "success")
        return redirect(url_for('company_bp.settings'))

    return render_template('company/settings.html', company=company)


# =====================================================
# LISTAR EMPRESAS (SUPER ADMIN)
# =====================================================

@company_bp.route('/list-companies')
def list_companies():
    user = require_login()
    if not user:
        return redirect(url_for('login_bp.login'))

    if session.get('user_role') != 'superadmin':
        flash("Acceso denegado", "danger")
        return redirect(url_for('dashboard_bp.dashboard'))

    return redirect(url_for('superadmin_bp.clients'))


# =====================================================
# IMPERSONAR EMPRESA
# =====================================================

@company_bp.route('/impersonate/<int:company_id>', methods=['POST'])
def impersonate_company(company_id):
    user = require_login()
    if not user:
        return redirect(url_for('login_bp.login'))

    if session.get('user_role') != 'superadmin':
        flash("Acceso denegado", "danger")
        return redirect(url_for('dashboard_bp.dashboard'))

    target_company = Company.query.get(company_id)
    if not target_company:
        flash("Empresa no encontrada", "danger")
        return redirect(url_for('company_bp.list_companies'))

    if 'original_user_id' not in session:
        session['original_user_id'] = user.id

    session['company_id'] = target_company.id
    session['company_name'] = target_company.name
    session['impersonating'] = True

    flash(f"Ahora estás viendo como {target_company.name}", "info")
    return redirect(url_for('dashboard_bp.dashboard'))


# =====================================================
# DETENER IMPERSONACIÓN
# =====================================================

@company_bp.route('/stop-impersonate', methods=['POST'])
def stop_impersonate():
    original_user_id = session.get('original_user_id')
    if not original_user_id:
        return redirect(url_for('dashboard_bp.dashboard'))

    original_user = User.query.get(original_user_id)
    if not original_user:
        return redirect(url_for('dashboard_bp.dashboard'))

    refresh_session_user(original_user)
    session.pop('impersonating', None)
    session.pop('original_user_id', None)

    flash("Sesión restaurada", "success")
    return redirect(url_for('superadmin_bp.clients'))


# =====================================================
# SUBIR COMPROBANTE (Actualiza almacenamiento)
# =====================================================
@company_bp.route('/upload-receipt', methods=['POST'])
def upload_receipt():
    user = require_login()
    if not user: return redirect(url_for('login_bp.login'))

    company = Company.query.get(session.get('company_id'))
    file = request.files.get('receipt')

    if company.receipt_status == 'PENDING':
        flash('Ya tienes un comprobante pendiente de revisión.', 'warning')
        return redirect(url_for('dashboard_bp.dashboard'))

    if file and file.filename:
        try:
            receipt_path = upload_file(file, "uploads/payments", company_id=company.id, private=True)
        except ValueError as error:
            flash(str(error), 'danger')
            return redirect(url_for('dashboard_bp.dashboard'))
        company.last_receipt_path = receipt_path
        company.receipt_status = "PENDING"
        company.status = True

        ahora = utcnow()
        if not company.expiration_date or company.expiration_date < ahora:
            company.grace_period_until = ahora + timedelta(hours=24)

        # 🔥 Recalcular barra de almacenamiento
        db.session.flush()
        company.current_storage_usage = get_dir_size(company.id)

        db.session.commit()
        session['subscription_status'] = 'GRACE_PERIOD'

        flash("¡Comprobante subido! Almacenamiento actualizado.", "success")
        return redirect(url_for('dashboard_bp.dashboard'))

    flash("Error al subir archivo", "danger")
    return redirect(url_for('dashboard_bp.dashboard'))

# =====================================================
# SOLICITAR CAMBIO DE PLAN
# =====================================================
@company_bp.route('/upgrade-plan', methods=['POST'])
def upgrade_plan():
    user = require_login()
    if not user: return redirect(url_for('login_bp.login'))

    company = Company.query.get(session.get('company_id'))
    selected_plan = (request.form.get('plan_type') or '').upper()
    file = request.files.get('receipt')

    if company.receipt_status == 'PENDING':
        flash('Ya tienes una solicitud de pago pendiente de revisión.', 'warning')
        return redirect(url_for('company_bp.view_plans'))

    if file and selected_plan in {'BASIC', 'PRO', 'ULTRA'}:
        try:
            path = upload_file(file, "uploads/payments", company_id=company.id, private=True)
        except ValueError as error:
            flash(str(error), 'danger')
            return redirect(url_for('company_bp.view_plans'))

        company.last_receipt_path = path
        company.receipt_status = "PENDING"
        company.requested_plan = selected_plan
        company.plan_status = "UPGRADING"

        ahora = utcnow()
        if not company.expiration_date or company.expiration_date < ahora:
            company.grace_period_until = ahora + timedelta(hours=24)

        # 🔥 Recalcular barra de almacenamiento
        db.session.flush()
        company.current_storage_usage = get_dir_size(company.id)

        db.session.commit()
        flash(f"Solicitud para el plan {selected_plan} enviada.", "success")
        return redirect(url_for('dashboard_bp.dashboard'))

    flash("Error al procesar la solicitud.", "danger")
    return redirect(url_for('company_bp.view_plans'))

@company_bp.route('/plans')
def view_plans():
    user = require_login()
    if not user:
        return redirect(url_for('login_bp.login'))

    company_id = session.get('company_id')
    company = Company.query.get_or_404(company_id)

    days_remaining = 0
    if company.expiration_date:
        fecha_vencimiento = company.expiration_date.date()
        hoy = utcnow().date()

        delta = fecha_vencimiento - hoy
        days_remaining = delta.days

        if days_remaining < 0:
            days_remaining = 0

    price_defaults = {'BASIC': '29', 'PRO': '69', 'ULTRA': '149'}
    plan_names = {'BASIC': 'Básico', 'PRO': 'Profesional', 'ULTRA': 'Enterprise'}
    plans = []
    for plan_id in ('BASIC', 'PRO', 'ULTRA'):
        limits = PLAN_LIMITS[plan_id]
        plans.append({
            'id': plan_id,
            'name': plan_names[plan_id],
            'price': current_app.config.get(f'PLAN_{plan_id}_PRICE_USD', price_defaults[plan_id]),
            'max_warehouses': limits['max_warehouses'],
            'max_users': limits['max_users'],
            'max_monthly_invoices': limits['max_monthly_invoices'],
            'storage_mb': limits['storage_bytes'] // (1024 * 1024),
        })

    return render_template(
        'company/plans.html', company=company, days_remaining=days_remaining, plans=plans
    )
