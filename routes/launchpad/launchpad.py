from flask import Blueprint, render_template, session, redirect, url_for
from models.user.user import User

launchpad_bp = Blueprint('launchpad_bp', __name__)

@launchpad_bp.route('/launchpad')
def launchpad():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)
    
    # --- LA CLAVE ESTÁ AQUÍ ---
    session['tablet_mode'] = True 
    # --------------------------

    modules = [
        {"name": "Ventas", "icon": "bi-graph-up-arrow", "route": "/sales", "color": "#ff2d55"},
        {"name": "Inventario", "icon": "bi-box-seam-fill", "route": "/list_product", "color": "#ffcc00"},
        {"name": "Almacenes", "icon": "bi-building-fill", "route": url_for('warehouse_bp.list_warehouses'), "color": "#5856d6"},
        {"name": "CRM", "icon": "bi-people-fill", "route": "/crm", "color": "#007aff"},
        {"name": "Transferencias", "icon": "bi-arrow-left-right", "route": url_for('transfer_bp.transfers'), "color": "#34c759"},
        {"name": "Escáner", "icon": "bi-qr-code-scan", "route": url_for('transfer_bp.scanner_mode'), "color": "#af52de"},
        {"name": "Kardex", "icon": "bi-journal-text", "route": "/kardex", "color": "#ff9500"},
        {"name": "Configuración", "icon": "bi-gear-wide-connected", "route": url_for('company_bp.settings'), "color": "#8e8e93"},
    ]
    
    return render_template('launchpad/index.html', user=user, modules=modules)

@launchpad_bp.route('/exit-tablet')
def exit_tablet():
    session.pop('tablet_mode', None)
    return redirect(url_for('dashboard_bp.dashboard')) 