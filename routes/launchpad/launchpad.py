from flask import Blueprint, render_template, session, redirect, url_for
from models.user.user import User

launchpad_bp = Blueprint('launchpad_bp', __name__)

@launchpad_bp.route('/launchpad')
def launchpad():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)
    if not user:
        session.clear()
        return redirect(url_for('login_bp.login'))
    
    # --- LA CLAVE ESTÁ AQUÍ ---
    session['tablet_mode'] = True 
    # --------------------------

    definitions = [
        {"name": "Nueva venta", "description": "Cobrar y facturar", "icon": "bi-plus-circle", "route": url_for('sales_bp.create_sale'), "permission": "sales.create", "featured": True},
        {"name": "Ventas", "description": "Historial y cotizaciones", "icon": "bi-receipt", "route": url_for('sales_bp.list_sales'), "permission": "sales.view"},
        {"name": "Productos", "description": "Catálogo y servicios", "icon": "bi-box-seam", "route": "/list_product", "permission": "products.view"},
        {"name": "Existencias", "description": "Stock disponible", "icon": "bi-boxes", "route": "/stock", "permission": "stock.view"},
        {"name": "Almacenes", "description": "Sedes y ubicaciones", "icon": "bi-building", "route": url_for('warehouse_bp.list_warehouses'), "permission": "warehouses.view"},
        {"name": "Transferencias", "description": "Mover inventario", "icon": "bi-arrow-left-right", "route": url_for('transfer_bp.transfers'), "permission": "transfers.view"},
        {"name": "Escáner", "description": "Validación por código", "icon": "bi-upc-scan", "route": url_for('transfer_bp.scanner_mode'), "permission": "transfers.scanner"},
        {"name": "Clientes", "description": "Directorio comercial", "icon": "bi-people", "route": url_for('client_bp.list_clients'), "permission": "clients.view"},
        {"name": "CRM", "description": "Seguimientos y tareas", "icon": "bi-chat-square-heart", "route": url_for('crm_bp.crm_index'), "permission": "crm.view"},
        {"name": "Compras", "description": "Órdenes y recepción", "icon": "bi-bag-check", "route": url_for('purchase_bp.purchase_list'), "permission": "purchases.view"},
        {"name": "Proveedores", "description": "Socios de suministro", "icon": "bi-truck", "route": url_for('supplier_bp.supplier_list'), "permission": "suppliers.view"},
        {"name": "Kardex", "description": "Trazabilidad del stock", "icon": "bi-list-check", "route": url_for('stock_bp.kardex_general'), "permission": "stock.kardex"},
        {"name": "Caja", "description": "Cierre y cuadre", "icon": "bi-cash-coin", "route": url_for('cash_bp.close_cash'), "permission": "cash.view"},
        {"name": "Reportes", "description": "Indicadores del negocio", "icon": "bi-bar-chart", "route": url_for('reports_bp.index'), "permission": "reports.view"},
        {"name": "Configuración", "description": "Datos de empresa", "icon": "bi-gear", "route": url_for('company_bp.settings'), "permission": "company.settings"},
    ]
    modules = [module for module in definitions if user.has_permission(module['permission'])]

    return render_template('launchpad/index.html', user=user, modules=modules)

@launchpad_bp.route('/exit-tablet')
def exit_tablet():
    session.pop('tablet_mode', None)
    return redirect(url_for('dashboard_bp.dashboard'))
