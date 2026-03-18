from flask import Blueprint, render_template, session, redirect, url_for, request, flash, jsonify
from models.user.user import User
from models.warehouse.warehouse import Warehouse
from db import db
from flask_mail import Message
from itsdangerous import SignatureExpired, BadTimeSignature

users_bp = Blueprint('users_bp', __name__)

# =========================
# LISTAR USUARIOS DE LA EMPRESA
# =========================
@users_bp.route('/users')
def users():
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    
    if not user_id or not company_id:
        flash('Debes iniciar sesión', 'warning')
        return redirect(url_for('login_bp.login'))

    current_user = User.query.get(user_id)

    users_list = User.query.filter_by(company_id=company_id).all()
    
    return render_template('users/users.html', users=users_list, user=current_user)


# =========================
# API USUARIOS
# =========================
@users_bp.route('/users_api')
def users_api():
    user_list = User.query.all()

    return jsonify(
        {
            'data': str(user_list)
        }
    )


# =========================
# PERFIL DE USUARIO
# =========================
@users_bp.route('/users/<int:id>')
def user_profile(id):
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    current_user = User.query.get(user_id)
    
    target_user = User.query.filter_by(id=id, company_id=company_id).first_or_404()
    
    return render_template(
        'users/users_profile.html',
        target_user=target_user,
        user=current_user
    )

# =========================
# CREAR USUARIO CON LÍMITES DE PLAN
# =========================
@users_bp.route('/create_user', methods=['GET', 'POST'])
def create_user():
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    current_user = User.query.get(user_id)
    
    from models.company.company import Company
    company = Company.query.get(company_id)
    plan_limits = company.get_plan_limits() 
    
    current_users_count = User.query.filter_by(company_id=company_id).count()

    if request.method == 'POST':
        if current_users_count >= plan_limits['max_users']:
            flash(f"Límite de usuarios alcanzado para el plan {company.plan_name}. Tu plan permite un máximo de {plan_limits['max_users']} usuarios.", 'danger')
            return redirect(url_for('users_bp.users'))

        email = request.form.get('email')
        name = request.form.get('name')
        password = request.form.get('password')
        role = request.form.get('role')
        cedula = request.form.get('cedula')
        warehouse_id = request.form.get('warehouse_id')

        if not email or not name or not password or not role or not cedula:
            flash('Todos los campos son obligatorios', 'danger')
            return redirect(url_for('users_bp.create_user'))

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Este correo electrónico ya está registrado', 'danger')
            return redirect(url_for('users_bp.create_user'))

        w_id = int(warehouse_id) if warehouse_id and warehouse_id != "" else None

        new_user = User(
            email=email,
            name=name,
            password=password,
            role=role,
            cedula=cedula,
            warehouse_id=w_id,
            company_id=company_id
        )

        try:
            db.session.add(new_user)
            db.session.commit()
            flash(f'Usuario {name} creado exitosamente en el plan {company.plan_name}', 'success')
            return redirect(url_for('users_bp.users'))
        except Exception as e:
            db.session.rollback()
            flash('Error interno al guardar el usuario', 'danger')
            print(f"Error: {e}")
            return redirect(url_for('users_bp.create_user'))
    
    warehouses = Warehouse.query.filter_by(
        status=True,
        company_id=company_id
    ).all()

    return render_template(
        'users/create_user.html',
        warehouses=warehouses,
        user=current_user,
        plan_limits=plan_limits,          
        current_users_count=current_users_count
    )

@users_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
def edit_user(id):
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    current_user = User.query.get(user_id)
    target_user = User.query.filter_by(
        id=id,
        company_id=company_id
    ).first_or_404()

    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        role = request.form.get('role')
        cedula = request.form.get('cedula')
        password = request.form.get('password')
        warehouse_id = request.form.get('warehouse_id')
        # NUEVO: Capturar divisa
        default_currency = request.form.get('default_currency', 'DOP')

        if not name or not email or not role or not cedula:
            flash('Todos los campos obligatorios deben completarse', 'danger')
            return redirect(url_for('users_bp.edit_user', id=id))

        target_user.name = name
        target_user.email = email
        target_user.role = role
        target_user.cedula = cedula
        target_user.default_currency = default_currency # GUARDAR EN DB

        if password and password.strip() != "":
            target_user.password = password
        
        target_user.warehouse_id = int(warehouse_id) if warehouse_id and warehouse_id != "" else None

        if current_user.id == target_user.id:
            session['selected_currency'] = default_currency

        db.session.commit()
        flash('Información de usuario actualizada correctamente', 'success')
        return redirect(url_for('users_bp.users'))

    warehouses = Warehouse.query.filter_by(
        status=True,
        company_id=company_id
    ).all()

    return render_template(
        'users/edit_user.html',
        target_user=target_user,
        warehouses=warehouses,
        user=current_user
    )

# =========================
# ELIMINAR USUARIO
# =========================
@users_bp.route('/delete/<int:id>', methods=['POST'])
def delete_user(id):
    company_id = session.get('company_id')
    current_user_id = session.get('user_id')
    
    if not company_id:
        return redirect(url_for('login_bp.login'))

    if current_user_id == id:
        flash('No puedes eliminar tu propia cuenta', 'danger')
        return redirect(url_for('users_bp.users'))

    user_to_delete = User.query.filter_by(
        id=id,
        company_id=company_id
    ).first_or_404()

    db.session.delete(user_to_delete)
    db.session.commit()
    
    flash('Usuario eliminado', 'info')
    return redirect(url_for('users_bp.users'))


# =========================
# ENTRADA / DETALLE USUARIO
# =========================
@users_bp.route('/entrada/<int:id>')
def entrada_user(id):
    user_id = session.get('user_id')
    company_id = session.get('company_id')

    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    current_user = User.query.get(user_id)

    target_user = User.query.filter_by(
        id=id,
        company_id=company_id
    ).first_or_404()

    return render_template(
        'users/users_profile.html',
        target_user=target_user,
        user=current_user
    )

@users_bp.route('/request_password_reset/<int:id>', methods=['POST'])
def request_password_reset(id):
    from app import mail, s # Importación local
    target_user = User.query.get_or_404(id)
    token = s.dumps(target_user.email, salt='password-reset-salt')
    link = url_for('users_bp.reset_with_token', token=token, _external=True)

    msg = Message("🔒 Restablecimiento de Contraseña - OrbisERP", recipients=[target_user.email])
    msg.body = f"Se ha solicitado un cambio de clave para {target_user.name}. Link: {link}"
    
    try:
        mail.send(msg)
        flash(f"Correo enviado a {target_user.email}", "success")
    except Exception as e:
        flash("Error de envío.", "danger")
        print(e)

    return redirect(url_for('users_bp.edit_user', id=id))

@users_bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_with_token(token):
    from app import s # Importación local
    try:
        email = s.loads(token, salt='password-reset-salt', max_age=1800)
    except (SignatureExpired, BadTimeSignature):
        flash("El enlace expiró o es inválido.", "danger")
        return redirect(url_for('login_bp.login'))

    user_to_update = User.query.filter_by(email=email).first_or_404()

    if request.method == 'POST':
        nueva_clave = request.form.get('password')
        user_to_update.password = nueva_clave 
        db.session.commit()
        flash("Contraseña actualizada.", "success")
        return redirect(url_for('login_bp.login'))

    return render_template('users/reset_password_form.html', token=token)