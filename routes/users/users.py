from services.time_utils import utcnow
from datetime import datetime
from decimal import Decimal
from flask import Blueprint, render_template, session, redirect, url_for, request, flash, jsonify, current_app
from models.user.user import User
from models.warehouse.warehouse import Warehouse
from models.retail import Branch, PosTerminal
from models.auditoria.auditoria import AuditLog
from models.sales.sales import Sale
from models.stock_movement.stock_movement import StockMovement
from models.stock_transfer.stock_transfer import StockTransfer
from models.warehouse_stock.warehouse_stock import WarehouseStock
from permissions import ALL_PERMISSIONS, PERMISSION_GROUPS, PROFILE_PRESETS
from db import db
from flask_mail import Message
from itsdangerous import SignatureExpired, BadTimeSignature
from sqlalchemy import func, or_
from security import password_error
from services.validation import BusinessRuleError, tenant_id

users_bp = Blueprint('users_bp', __name__)


def _resolve_retail_assignment(company_id, warehouse_id=None, branch_id=None, terminal_id=None, *, require_pos_context=False):
    """Resolve an explicit, tenant-safe branch/warehouse/POS assignment.

    A selected terminal never silently overrides conflicting form values. Standard
    operational users can require a complete POS context so sales cannot drift to
    another branch or warehouse.
    """
    warehouse = None
    branch = None
    terminal = None
    requested_warehouse_id = int(warehouse_id) if warehouse_id else None
    requested_branch_id = int(branch_id) if branch_id else None

    if requested_warehouse_id:
        warehouse = Warehouse.query.filter_by(id=requested_warehouse_id, company_id=company_id, status=True).first()
        if not warehouse:
            raise BusinessRuleError('El almacén seleccionado no pertenece a esta empresa o está inactivo.')
    if requested_branch_id:
        branch = Branch.query.filter_by(id=requested_branch_id, company_id=company_id, status=True).first()
        if not branch:
            raise BusinessRuleError('La sucursal seleccionada no pertenece a esta empresa o está inactiva.')

    if terminal_id:
        terminal = PosTerminal.query.filter_by(id=int(terminal_id), company_id=company_id, status=True).first()
        if not terminal:
            raise BusinessRuleError('La terminal POS seleccionada no pertenece a esta empresa o está inactiva.')
        if requested_warehouse_id and requested_warehouse_id != terminal.warehouse_id:
            raise BusinessRuleError(f'La terminal {terminal.name} pertenece a otro almacén. Corrige la asignación antes de guardar.')
        if requested_branch_id and terminal.branch_id and requested_branch_id != terminal.branch_id:
            raise BusinessRuleError(f'La terminal {terminal.name} pertenece a otra sucursal. Corrige la asignación antes de guardar.')
        warehouse = terminal.warehouse
        branch = terminal.branch or branch

    if warehouse and branch and warehouse.branch_id and warehouse.branch_id != branch.id:
        raise BusinessRuleError('El almacén seleccionado pertenece a otra sucursal.')
    if warehouse and not branch and warehouse.branch_id:
        branch = warehouse.branch

    if require_pos_context:
        if not terminal:
            raise BusinessRuleError('Asigna una terminal POS al usuario operativo.')
        if not terminal.branch_id:
            raise BusinessRuleError('La terminal POS debe estar vinculada a una sucursal antes de asignarla a un usuario operativo.')
        if not branch:
            raise BusinessRuleError('Asigna una sucursal al usuario operativo. La terminal POS debe estar vinculada a esa sucursal.')
        if not warehouse:
            raise BusinessRuleError('La terminal POS debe estar vinculada a un almacén activo.')

    return warehouse.id if warehouse else None, branch.id if branch else None, terminal.id if terminal else None

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

    if not current_user.has_permission('users.view'):
        return redirect(url_for('dashboard_bp.dashboard'))

    users_list = User.query.filter_by(company_id=company_id, is_active=True).all()
    
    return render_template('users/users.html', users=users_list, user=current_user)


# =========================
# API USUARIOS
# =========================
@users_bp.route('/users_api')
def users_api():
    company_id = session.get('company_id')
    user_id = session.get('user_id')
    if not user_id or not company_id:
        return jsonify({'error': 'No autenticado'}), 401
    current_user = User.query.filter_by(id=user_id, company_id=company_id, is_active=True).first()
    if not current_user or not current_user.has_permission('users.view'):
        return jsonify({'error': 'No autorizado'}), 403
    user_list = User.query.filter_by(company_id=company_id, is_active=True).all()
    return jsonify({'data': [
        {'id': item.id, 'name': item.name, 'email': item.email, 'role': item.role}
        for item in user_list
    ]})


@users_bp.route('/users/permission-audit')
def permission_audit():
    company_id = session.get('company_id')
    user_id = session.get('user_id')
    if not company_id or not user_id:
        return redirect(url_for('login_bp.login'))
    current_user = User.query.filter_by(id=user_id, company_id=company_id, is_active=True).first()
    if not current_user or not current_user.has_permission('audits.view'):
        flash('No tienes permiso para revisar la auditoría de usuarios.', 'danger')
        return redirect(url_for('users_bp.users'))
    logs = AuditLog.query.filter_by(
        company_id=company_id,
        action='USER_PERMISSIONS_UPDATED',
    ).order_by(AuditLog.created_at.desc()).limit(250).all()
    actor_ids = {log.user_id for log in logs if log.user_id}
    actors = {row.id: row for row in User.query.filter(User.id.in_(actor_ids)).all()} if actor_ids else {}
    return render_template('users/permission_audit.html', logs=logs, actors=actors, user=current_user)


# =========================
# PERFIL / ACTIVIDAD DE USUARIO
# =========================
def _user_activity_context(company_id, target_user):
    sales = Sale.query.filter_by(company_id=company_id, user_id=target_user.id).order_by(Sale.created_at.desc()).limit(30).all()
    movements = StockMovement.query.filter_by(company_id=company_id, user_id=target_user.id).order_by(StockMovement.created_at.desc()).limit(40).all()
    transfers = StockTransfer.query.filter(
        StockTransfer.company_id == company_id,
        or_(StockTransfer.created_by_id == target_user.id, StockTransfer.received_by_id == target_user.id),
    ).order_by(StockTransfer.created_at.desc()).limit(30).all()
    logs = AuditLog.query.filter_by(company_id=company_id, user_id=target_user.id).order_by(AuditLog.created_at.desc()).limit(40).all()
    warehouse_stock = []
    if target_user.warehouse_id:
        warehouse_stock = WarehouseStock.query.filter_by(
            company_id=company_id, warehouse_id=target_user.warehouse_id
        ).order_by(WarehouseStock.quantity.desc()).limit(30).all()

    sales_stats = db.session.query(
        func.count(Sale.id), func.coalesce(func.sum(Sale.total), 0)
    ).filter(
        Sale.company_id == company_id, Sale.user_id == target_user.id, Sale.status == 'COMPLETED'
    ).one()
    return {
        'sales': sales,
        'movements': movements,
        'transfers': transfers,
        'logs': logs,
        'warehouse_stock': warehouse_stock,
        'activity_stats': {
            'completed_sales': int(sales_stats[0] or 0),
            'sales_total': Decimal(sales_stats[1] or 0),
            'movements': StockMovement.query.filter_by(company_id=company_id, user_id=target_user.id).count(),
            'transfers': StockTransfer.query.filter(
                StockTransfer.company_id == company_id,
                or_(StockTransfer.created_by_id == target_user.id, StockTransfer.received_by_id == target_user.id),
            ).count(),
        },
    }


@users_bp.route('/users/<int:id>')
def user_profile(id):
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))
    current_user = User.query.filter_by(id=user_id, company_id=company_id).first_or_404()
    if not current_user.has_permission('users.view'):
        flash('No tienes permiso para ver la actividad de usuarios.', 'danger')
        return redirect(url_for('dashboard_bp.dashboard'))
    target_user = User.query.filter_by(id=id, company_id=company_id).first_or_404()
    return render_template(
        'users/users_profile.html', target_user=target_user, user=current_user,
        **_user_activity_context(company_id, target_user),
    )

# =========================
# CREAR USUARIO CON HERENCIA DE DIVISA
# =========================
@users_bp.route('/create_user', methods=['GET', 'POST'])
def create_user():
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))

    current_user = db.session.get(User, user_id)
    
    from models.company.company import Company
    company = db.session.get(Company, company_id)
    plan_limits = company.get_plan_limits() 
    
    current_users_count = User.query.filter_by(company_id=company_id, is_active=True).count()

    if not current_user.has_permission('users.create'):
        flash('No tienes permiso para crear usuarios.', 'danger')
        return redirect(url_for('users_bp.users'))

    if request.method == 'POST':
        if current_users_count >= plan_limits['max_users']:
            flash(f"Límite de usuarios alcanzado. Máximo: {plan_limits['max_users']}", 'danger')
            return redirect(url_for('users_bp.users'))

        email = (request.form.get('email') or '').strip().lower()
        name = (request.form.get('name') or '').strip()
        password = request.form.get('password')
        role = request.form.get('role')
        cedula = request.form.get('cedula')
        warehouse_id = request.form.get('warehouse_id')
        branch_id = request.form.get('branch_id')
        terminal_id = request.form.get('terminal_id')
        is_active = request.form.get('is_active') == 'on'

        inherited_currency = company.default_currency if hasattr(company, 'default_currency') and company.default_currency else current_user.default_currency
        if not inherited_currency:
            inherited_currency = 'DOP'

        if not email or not name or not password or not role or not cedula:
            flash('Todos los campos son obligatorios', 'danger')
            return redirect(url_for('users_bp.create_user'))
        if role not in {'user', 'admin'} or (role == 'admin' and current_user.role not in {'admin', 'superadmin'}):
            flash('El rol seleccionado no es válido.', 'danger')
            return redirect(url_for('users_bp.create_user'))
        issue = password_error(password)
        if issue:
            flash(issue, 'danger')
            return redirect(url_for('users_bp.create_user'))

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Este correo electrónico ya está registrado', 'danger')
            return redirect(url_for('users_bp.create_user'))

        try:
            w_id, b_id, t_id = _resolve_retail_assignment(company_id, warehouse_id, branch_id, terminal_id, require_pos_context=(role == 'user'))
        except (BusinessRuleError, TypeError, ValueError) as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('users_bp.create_user'))

        new_user = User(
            email=email,
            name=name,
            password='pending-hash',
            role=role,
            cedula=cedula,
            warehouse_id=w_id,
            branch_id=b_id,
            terminal_id=t_id,
            company_id=company_id,
            is_active=is_active,
            email_verified_at=utcnow(),
            default_currency=inherited_currency # SE ASIGNA AQUÍ
        )
        new_user.set_password(password)
        new_user.set_permissions(PROFILE_PRESETS['seller'])

        try:
            db.session.add(new_user)
            db.session.commit()
            flash(f'Usuario {name} creado con divisa {inherited_currency}', 'success')
            return redirect(url_for('users_bp.users'))
        except Exception:
            db.session.rollback()
            current_app.logger.exception('No se pudo crear el usuario email=%s company_id=%s', email, company_id)
            flash('Error al guardar el usuario', 'danger')
            return redirect(url_for('users_bp.create_user'))
    
    warehouses = Warehouse.query.filter_by(status=True, company_id=company_id).all()
    branches = Branch.query.filter_by(status=True, company_id=company_id).order_by(Branch.is_main.desc(), Branch.name.asc()).all()
    terminals = PosTerminal.query.filter_by(status=True, company_id=company_id).order_by(PosTerminal.name.asc()).all()

    return render_template(
        'users/create_user.html',
        warehouses=warehouses,
        branches=branches,
        terminals=terminals,
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

    if not current_user.has_permission('users.edit'):
        flash('No tienes permiso para editar usuarios.', 'danger')
        return redirect(url_for('users_bp.users'))
    if target_user.role in {'admin', 'superadmin'} and current_user.role not in {'admin', 'superadmin'}:
        flash('No puedes modificar una cuenta administrativa.', 'danger')
        return redirect(url_for('users_bp.users'))

    if request.method == 'POST':
        name = request.form.get('name')
        email = (request.form.get('email') or '').strip().lower()
        role = request.form.get('role')
        cedula = request.form.get('cedula')
        password = request.form.get('password')
        warehouse_id = request.form.get('warehouse_id')
        branch_id = request.form.get('branch_id')
        terminal_id = request.form.get('terminal_id')
        # NUEVO: Capturar divisa
        default_currency = request.form.get('default_currency', 'DOP')

        if not name or not email or not role or not cedula:
            flash('Todos los campos obligatorios deben completarse', 'danger')
            return redirect(url_for('users_bp.edit_user', id=id))

        if role not in {'user', 'admin'} or (role == 'admin' and current_user.role not in {'admin', 'superadmin'}):
            flash('No puedes conceder un rol administrativo.', 'danger')
            return redirect(url_for('users_bp.edit_user', id=id))
        if current_user.id == target_user.id and target_user.role == 'admin' and role != 'admin':
            flash('No puedes retirar tu propio rol de administrador.', 'danger')
            return redirect(url_for('users_bp.edit_user', id=id))

        duplicate_email = User.query.filter(User.email == email, User.id != target_user.id).first()
        if duplicate_email:
            flash('Este correo electrónico ya está registrado.', 'danger')
            return redirect(url_for('users_bp.edit_user', id=id))

        before_permissions = sorted(target_user.permission_set())
        requested_permissions = request.form.getlist('permissions')

        target_user.name = name
        target_user.email = email
        target_user.role = role
        target_user.cedula = cedula
        target_user.default_currency = default_currency # GUARDAR EN DB
        if role == 'user':
            target_user.set_permissions(requested_permissions)

        if password and password.strip() != "":
            issue = password_error(password)
            if issue:
                flash(issue, 'danger')
                return redirect(url_for('users_bp.edit_user', id=id))
            target_user.set_password(password)
        
        try:
            w_id, b_id, t_id = _resolve_retail_assignment(company_id, warehouse_id, branch_id, terminal_id, require_pos_context=(role == 'user'))
            target_user.warehouse_id = w_id
            target_user.branch_id = b_id
            target_user.terminal_id = t_id
        except (BusinessRuleError, TypeError, ValueError) as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('users_bp.edit_user', id=id))

        # Ordinary edits are live: permissions and assignments are read from the
        # database on every request. Password changes still revoke sessions via
        # User.set_password(), which is the intentional security boundary.
        if current_user.id == target_user.id:
            session['selected_currency'] = default_currency
            session['user_name'] = target_user.name
            session['user_role'] = target_user.role
            session['company_id'] = target_user.company_id
            session['warehouse_id'] = target_user.warehouse_id
            session['branch_id'] = target_user.branch_id
            session['terminal_id'] = target_user.terminal_id

        after_permissions = sorted(target_user.permission_set())
        added = sorted(set(after_permissions) - set(before_permissions))
        removed = sorted(set(before_permissions) - set(after_permissions))
        db.session.add(AuditLog(
            company_id=company_id,
            user_id=current_user.id,
            action='USER_PERMISSIONS_UPDATED',
            description=(f'Permisos de {target_user.name} (#{target_user.id}) actualizados. '
                         f'Agregados: {", ".join(added) or "ninguno"}. '
                         f'Retirados: {", ".join(removed) or "ninguno"}.'),
            ip_address=request.remote_addr,
        ))
        db.session.commit()
        flash('Información de usuario actualizada correctamente', 'success')
        return redirect(url_for('users_bp.users'))

    warehouses = Warehouse.query.filter_by(
        status=True,
        company_id=company_id
    ).all()
    branches = Branch.query.filter_by(status=True, company_id=company_id).order_by(Branch.is_main.desc(), Branch.name.asc()).all()
    terminals = PosTerminal.query.filter_by(status=True, company_id=company_id).order_by(PosTerminal.name.asc()).all()

    return render_template(
        'users/edit_user.html',
        target_user=target_user,
        warehouses=warehouses,
        branches=branches,
        terminals=terminals,
        user=current_user,
        permission_groups=PERMISSION_GROUPS,
        permission_presets={name: sorted(values) for name, values in PROFILE_PRESETS.items() if name != 'operational'},
        selected_permissions=target_user.permission_set(),
        permission_total=len(ALL_PERMISSIONS),
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

    current_user = db.session.get(User, current_user_id)
    if not current_user or not current_user.has_permission('users.delete'):
        flash('No tienes permiso para eliminar usuarios.', 'danger')
        return redirect(url_for('users_bp.users'))

    user_to_delete = User.query.filter_by(
        id=id,
        company_id=company_id
    ).first_or_404()

    user_to_delete.is_active = False
    user_to_delete.session_version = int(user_to_delete.session_version or 1) + 1
    db.session.add(AuditLog(
        company_id=company_id, user_id=current_user_id, action='USER_DEACTIVATED',
        description=f'Usuario {user_to_delete.name} (#{user_to_delete.id}) desactivado.',
        ip_address=request.remote_addr,
    ))
    db.session.commit()

    flash('Usuario desactivado y sesiones revocadas.', 'info')
    return redirect(url_for('users_bp.users'))


# =========================
# ENTRADA / DETALLE USUARIO (alias legado)
# =========================
@users_bp.route('/entrada/<int:id>')
def entrada_user(id):
    return redirect(url_for('users_bp.user_profile', id=id))

@users_bp.route('/request_password_reset/<int:id>', methods=['POST'])
def request_password_reset(id):
    from app import mail, s # Importación local
    company_id = session.get('company_id')
    user_id = session.get('user_id')
    if not user_id or not company_id:
        return redirect(url_for('login_bp.login'))
    current_user = User.query.filter_by(id=user_id, company_id=company_id, is_active=True).first()
    if not current_user or not current_user.has_permission('users.reset_password'):
        flash('No tienes permiso para restablecer contraseñas de usuarios.', 'danger')
        return redirect(url_for('users_bp.users'))
    target_user = User.query.filter_by(id=id, company_id=company_id).first_or_404()
    if target_user.role in {'admin', 'superadmin'} and current_user.role not in {'admin', 'superadmin'}:
        flash('No puedes restablecer una cuenta administrativa.', 'danger')
        return redirect(url_for('users_bp.users'))
    token = s.dumps(
        {'email': target_user.email, 'version': int(target_user.session_version or 1)},
        salt='password-reset-salt',
    )
    reset_path = url_for('users_bp.reset_with_token', token=token)
    base = current_app.config.get('PUBLIC_BASE_URL')
    link = f'{base}{reset_path}' if base else url_for('users_bp.reset_with_token', token=token, _external=True)

    msg = Message("🔒 Restablecimiento de Contraseña - OrbisERP", recipients=[target_user.email])
    msg.body = f"Se ha solicitado un cambio de clave para {target_user.name}. Link: {link}"
    
    try:
        mail.send(msg)
        flash(f"Correo enviado a {target_user.email}", "success")
    except Exception:
        current_app.logger.exception('No se pudo enviar restablecimiento administrativo para user_id=%s', target_user.id)
        flash("No se pudo enviar el correo. Revisa la configuración SMTP.", "danger")

    return redirect(url_for('users_bp.edit_user', id=id))

@users_bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_with_token(token):
    from app import s # Importación local
    try:
        token_data = s.loads(token, salt='password-reset-salt', max_age=1800)
    except (SignatureExpired, BadTimeSignature):
        flash("El enlace expiró o es inválido.", "danger")
        return redirect(url_for('login_bp.login'))

    if not isinstance(token_data, dict) or not token_data.get('email'):
        flash("El enlace expiró o es inválido.", "danger")
        return redirect(url_for('login_bp.login'))
    user_to_update = User.query.filter_by(email=token_data['email'], is_active=True).first_or_404()
    if int(token_data.get('version') or 0) != int(user_to_update.session_version or 1):
        flash("Este enlace ya fue utilizado o dejó de ser válido.", "danger")
        return redirect(url_for('login_bp.login'))

    if request.method == 'POST':
        nueva_clave = request.form.get('password')
        issue = password_error(nueva_clave)
        if issue:
            flash(issue, "danger")
            return render_template('users/reset_password_form.html', token=token)
        user_to_update.set_password(nueva_clave)
        db.session.commit()
        flash("Contraseña actualizada.", "success")
        return redirect(url_for('login_bp.login'))

    return render_template('users/reset_password_form.html', token=token)
