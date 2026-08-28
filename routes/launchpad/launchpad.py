from flask import Blueprint, render_template, session, redirect, url_for, request
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
    
    if not session.get('tablet_mode'):
        return redirect(url_for('dashboard_bp.enable_tablet_mode'))

    definitions = [
        {"name": "Nueva venta", "description": "Cobrar y facturar", "icon": "bi-plus-circle", "route": url_for('sales_bp.create_sale', _tablet=1), "permission": "sales.create", "featured": True, "section": "sales"},
        {"name": "Caja", "description": "Abrir, cobrar y cuadrar esta sucursal", "icon": "bi-cash-coin", "route": url_for('cash_bp.register', _tablet=1), "permission": "cash.view", "section": "control"},
        {"name": "Ventas", "description": "Historial y cotizaciones", "icon": "bi-receipt", "route": url_for('sales_bp.list_sales', _tablet=1), "permission": "sales.view", "section": "sales"},
        {"name": "Devoluciones", "description": "Buscar la venta y procesar el retorno", "icon": "bi-arrow-return-left", "route": url_for('backoffice_bp.returns', _tablet=1), "permission": "sales.returns", "section": "sales"},
        {"name": "Garantías", "description": "Seguimiento y reemplazos", "icon": "bi-shield-check", "route": url_for('retail_bp.warranties', _tablet=1), "permission": "sales.warranties", "section": "sales"},
        {"name": "Productos", "description": "Catálogo y servicios", "icon": "bi-box-seam", "route": url_for('products_bp.list_products', _tablet=1), "permission": "products.view", "section": "inventory"},
        {"name": "Existencias", "description": "Stock disponible", "icon": "bi-boxes", "route": url_for('stock_bp.stock_actual', _tablet=1), "permission": "stock.view", "section": "inventory"},
        {"name": "Almacenes", "description": "Sedes y ubicaciones", "icon": "bi-building", "route": url_for('warehouse_bp.list_warehouses', _tablet=1), "permission": "warehouses.view", "section": "inventory"},
        {"name": "Transferencias", "description": "Mover inventario", "icon": "bi-arrow-left-right", "route": url_for('transfer_bp.transfers', _tablet=1), "permission": "transfers.view", "section": "inventory"},
        {"name": "Escáner", "description": "Validación por código", "icon": "bi-upc-scan", "route": url_for('transfer_bp.scanner_mode', _tablet=1), "permission": "transfers.scanner", "section": "inventory"},
        {"name": "Clientes", "description": "Directorio comercial", "icon": "bi-people", "route": url_for('client_bp.list_clients', _tablet=1), "permission": "clients.view", "section": "sales"},
        {"name": "CRM", "description": "Seguimientos y tareas", "icon": "bi-chat-square-heart", "route": url_for('crm_bp.crm_index', _tablet=1), "permission": "crm.view", "section": "sales"},
        {"name": "Compras", "description": "Órdenes y recepción", "icon": "bi-bag-check", "route": url_for('purchase_bp.purchase_list', _tablet=1), "permission": "purchases.view", "section": "purchases"},
        {"name": "Proveedores", "description": "Socios de suministro", "icon": "bi-truck", "route": url_for('supplier_bp.supplier_list', _tablet=1), "permission": "suppliers.view", "section": "purchases"},
        {"name": "Kardex", "description": "Trazabilidad del stock", "icon": "bi-list-check", "route": url_for('stock_bp.kardex_general', _tablet=1), "permission": "stock.kardex", "section": "inventory"},
        {"name": "Reportes", "description": "Indicadores del negocio", "icon": "bi-bar-chart", "route": url_for('reports_bp.index', _tablet=1), "permission": "reports.view", "section": "control"},
        {"name": "Configuración", "description": "Datos de empresa", "icon": "bi-gear", "route": url_for('company_bp.settings', _tablet=1), "permission": "company.settings", "section": "settings"},
    ]
    modules = [module for module in definitions if user.has_permission(module['permission'])]

    return render_template('launchpad/index.html', user=user, modules=modules)

@launchpad_bp.route('/exit-tablet')
def exit_tablet():
    session.pop('tablet_mode', None)
    session.modified = True
    response = redirect(url_for('dashboard_bp.dashboard'))
    response.set_cookie(
        'orbis_ui_mode', 'desktop', max_age=60 * 60 * 24 * 30, path='/',
        samesite='Lax', secure=request.is_secure, httponly=False
    )
    response.set_cookie(
        'orbis_tablet_mode', '0', max_age=60 * 60 * 24 * 30, path='/',
        samesite='Lax', secure=request.is_secure, httponly=False
    )
    return response
