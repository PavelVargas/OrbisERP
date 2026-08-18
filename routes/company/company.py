from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from models.company.company import Company
from models.user.user import User
from db import db
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
import os
import uuid
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


def upload_file(file, folder, company_id=None):
    """
    Versión mejorada: Si se pasa company_id, guarda en la carpeta técnica 
    de la empresa para que el monitor de almacenamiento pueda contarlo.
    """
    if file and file.filename:
        filename = secure_filename(file.filename)
        unique_name = f"{uuid.uuid4().hex}_{filename}"

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
        business_name = request.form.get('business_name')
        rnc = request.form.get('rnc')

        if not business_name:
            flash("El nombre es obligatorio", "danger")
            return redirect(url_for('company_bp.create_company'))

        new_company = Company(
            name=business_name,
            rnc=rnc,
            expiration_date=datetime.utcnow() + timedelta(days=30)
        )

        db.session.add(new_company)
        db.session.flush() 

        user.company_id = new_company.id
        user.role = 'admin'

        # Inicializar límites de almacenamiento según plan básico al crear
        limits = new_company.get_plan_limits()
        new_company.storage_limit = limits.get('storage_bytes', 524288000)

        db.session.commit()
        refresh_session_user(user)

        flash("Empresa creada correctamente", "success")
        return redirect(url_for('dashboard_bp.dashboard'))

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
        company.name = request.form.get('name')
        company.rnc = request.form.get('rnc')
        company.email = request.form.get('email')
        company.phone = request.form.get('phone')
        company.address = request.form.get('address')

        logo_file = request.files.get('logo')
        if logo_file and logo_file.filename:
            delete_file(company.logo)
            # Guardamos logo en la carpeta técnica de la empresa
            company.logo = upload_file(logo_file, "uploads/companies/logos", company_id=company.id)

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

    companies = Company.query.all()
    return render_template("company/list_companies.html", companies=companies, user=user)


# =====================================================
# IMPERSONAR EMPRESA
# =====================================================

@company_bp.route('/impersonate/<int:company_id>')
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

@company_bp.route('/stop-impersonate')
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
    return redirect(url_for('company_bp.list_companies'))


# =====================================================
# SUBIR COMPROBANTE (Actualiza almacenamiento)
# =====================================================
@company_bp.route('/upload-receipt', methods=['POST'])
def upload_receipt():
    user = require_login()
    if not user: return redirect(url_for('login_bp.login'))

    company = Company.query.get(session.get('company_id'))
    file = request.files.get('receipt')

    if file and file.filename:
        # Guardamos en la carpeta técnica de la empresa
        receipt_path = upload_file(file, "uploads/payments", company_id=company.id)
        company.last_receipt_path = receipt_path
        company.receipt_status = "PENDING"
        company.status = True 
        
        ahora = datetime.utcnow()
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
    selected_plan = request.form.get('plan_type') 
    file = request.files.get('receipt')

    if file and selected_plan:
        path = upload_file(file, "uploads/payments", company_id=company.id)
        
        company.last_receipt_path = path
        company.receipt_status = "PENDING"
        company.requested_plan = selected_plan 
        company.plan_status = "UPGRADING" 

        ahora = datetime.utcnow()
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
        hoy = datetime.utcnow().date()
        
        delta = fecha_vencimiento - hoy
        days_remaining = delta.days
    
        if days_remaining < 0:
            days_remaining = 0
            
    return render_template('company/plans.html', company=company, days_remaining=days_remaining)
