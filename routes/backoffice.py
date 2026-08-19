from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy import func, or_

from db import db
from models.auditoria.auditoria import AuditLog
from models.backoffice import (
    AppNotification, CustomerPayment, Expense, InventoryCount, InventoryCountItem,
    SaleReturn, SaleReturnItem, SupplierBill, SupplierPayment,
)
from models.client.client import Client
from models.products.products import Product, ProductType
from models.purchase.purchase_order import PurchaseOrder
from models.sales.sale_item import SaleItem
from models.sales.sales import Sale
from models.stock_movement.stock_movement import StockMovement
from models.supplier.supplier import Supplier
from models.user.user import User
from models.warehouse.warehouse import Warehouse
from models.warehouse_location.warehouse_location import LocationStock, WarehouseLocation
from models.warehouse_stock.warehouse_stock import WarehouseStock
from security import generate_totp_secret, verify_totp


backoffice_bp = Blueprint('backoffice_bp', __name__, url_prefix='/backoffice')


def _identity():
    company_id = session.get('company_id')
    user_id = session.get('user_id')
    if not company_id or not user_id:
        abort(401)
    return int(company_id), int(user_id)


def _money(raw, field='Monto'):
    try:
        value = Decimal(str(raw or '')).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        raise ValueError(f'{field} inválido.')
    if value <= 0:
        raise ValueError(f'{field} debe ser mayor que cero.')
    return value


def _audit(company_id, user_id, action, description):
    db.session.add(AuditLog(
        company_id=company_id, user_id=user_id, action=action,
        description=description[:1000], ip_address=(request.remote_addr or '')[:50],
    ))


def refresh_system_notifications(company_id):
    """Create actionable alerts once; the unique key prevents notification spam."""
    low_rows = db.session.query(Product.id, Product.name, func.sum(WarehouseStock.quantity).label('qty')).join(
        WarehouseStock, WarehouseStock.product_id == Product.id
    ).filter(Product.company_id == company_id, Product.status.is_(True)).group_by(Product.id, Product.name, Product.min_stock).having(
        func.sum(WarehouseStock.quantity) <= Product.min_stock
    ).limit(30).all()
    active_keys = set()
    for row in low_rows:
        key = f'low-stock:{row.id}'
        active_keys.add(key)
        if not AppNotification.query.filter_by(company_id=company_id, dedupe_key=key).first():
            db.session.add(AppNotification(
                company_id=company_id, level='WARNING', title='Stock bajo',
                message=f'{row.name} tiene {int(row.qty or 0)} unidades disponibles.',
                link=url_for('products_bp.view_product', product_id=row.id), dedupe_key=key,
            ))
    overdue = SupplierBill.query.filter(
        SupplierBill.company_id == company_id, SupplierBill.status != 'PAID',
        SupplierBill.due_date.isnot(None), SupplierBill.due_date < date.today(),
    ).limit(30).all()
    for bill in overdue:
        key = f'overdue-bill:{bill.id}'
        active_keys.add(key)
        if not AppNotification.query.filter_by(company_id=company_id, dedupe_key=key).first():
            db.session.add(AppNotification(
                company_id=company_id, level='DANGER', title='Cuenta vencida',
                message=f'La cuenta {bill.document_number} tiene un balance de RD$ {bill.balance:,.2f}.',
                link=url_for('backoffice_bp.payables'), dedupe_key=key,
            ))
    stale = AppNotification.query.filter(
        AppNotification.company_id == company_id,
        AppNotification.read_at.is_(None),
        or_(AppNotification.dedupe_key.like('low-stock:%'), AppNotification.dedupe_key.like('overdue-bill:%')),
    ).all()
    now = datetime.utcnow()
    for notification in stale:
        if notification.dedupe_key not in active_keys:
            notification.read_at = now
    db.session.commit()


@backoffice_bp.get('/')
def overview():
    company_id, user_id = _identity()
    receivable = db.session.query(func.coalesce(func.sum(Sale.balance), 0)).filter(
        Sale.company_id == company_id, Sale.status == 'COMPLETED', Sale.balance > 0,
    ).scalar()
    payable = db.session.query(func.coalesce(func.sum(SupplierBill.amount - SupplierBill.paid_amount), 0)).filter(
        SupplierBill.company_id == company_id, SupplierBill.status != 'PAID',
    ).scalar()
    month_start = date.today().replace(day=1)
    expenses = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.company_id == company_id, Expense.expense_date >= month_start,
    ).scalar()
    return_count = SaleReturn.query.filter_by(company_id=company_id).count()
    counts_pending = InventoryCount.query.filter_by(company_id=company_id, status='DRAFT').count()
    return render_template('backoffice/overview.html', user=db.session.get(User, user_id),
                           receivable=receivable, payable=payable, expenses=expenses,
                           return_count=return_count, counts_pending=counts_pending)


@backoffice_bp.route('/returns', methods=['GET'])
def returns():
    company_id, user_id = _identity()
    rows = SaleReturn.query.filter_by(company_id=company_id).order_by(SaleReturn.created_at.desc()).all()
    eligible_sales = Sale.query.filter_by(company_id=company_id, status='COMPLETED').order_by(Sale.created_at.desc()).limit(100).all()
    return render_template('backoffice/returns.html', user=db.session.get(User, user_id), rows=rows, eligible_sales=eligible_sales)


@backoffice_bp.route('/returns/new/<int:sale_id>', methods=['GET', 'POST'])
def create_return(sale_id):
    company_id, user_id = _identity()
    sale = Sale.query.filter_by(id=sale_id, company_id=company_id, status='COMPLETED').first_or_404()
    returned = dict(db.session.query(SaleReturnItem.sale_item_id, func.coalesce(func.sum(SaleReturnItem.quantity), 0)).join(
        SaleReturn, SaleReturn.id == SaleReturnItem.return_id
    ).filter(SaleReturn.company_id == company_id, SaleReturn.sale_id == sale.id,
             SaleReturn.status == 'COMPLETED').group_by(SaleReturnItem.sale_item_id).all())
    if request.method == 'POST':
        reason = (request.form.get('reason') or '').strip()
        if len(reason) < 3:
            flash('Indica el motivo de la devolución.', 'warning')
            return redirect(request.url)
        operation = SaleReturn(company_id=company_id, sale_id=sale.id, user_id=user_id,
                               reason=reason, refund_method=(request.form.get('refund_method') or 'ORIGINAL')[:30],
                               restocked=request.form.get('restock') == '1')
        total = Decimal('0')
        selected = 0
        try:
            for item in sale.items:
                qty = int(request.form.get(f'quantity_{item.id}', 0) or 0)
                available = int(item.quantity) - int(returned.get(item.id, 0) or 0)
                if qty < 0 or qty > available:
                    raise ValueError(f'Cantidad inválida para {item.product.name}.')
                if not qty:
                    continue
                selected += 1
                total += Decimal(item.price) * qty
                operation.items.append(SaleReturnItem(
                    sale_item_id=item.id, product_id=item.product_id, warehouse_id=item.warehouse_id,
                    quantity=qty, unit_price=item.price,
                ))
                if operation.restocked and item.warehouse_id and item.product.product_type != ProductType.SERVICE:
                    stock = WarehouseStock.query.filter_by(company_id=company_id, warehouse_id=item.warehouse_id,
                                                           product_id=item.product_id).with_for_update().first()
                    if not stock:
                        stock = WarehouseStock(company_id=company_id, warehouse_id=item.warehouse_id,
                                               product_id=item.product_id, quantity=0)
                        db.session.add(stock)
                    stock.quantity = int(stock.quantity or 0) + qty
                    db.session.add(StockMovement(company_id=company_id, warehouse_id=item.warehouse_id,
                                                 product_id=item.product_id, movement_type='IN', quantity=qty,
                                                 reason=f'Devolución venta #{sale.id}'))
            if not selected:
                raise ValueError('Selecciona al menos un producto.')
            operation.total_refund = total
            db.session.add(operation)
            db.session.flush()
            # Keep the sale as COMPLETED: the return is an immutable linked
            # operation and reports subtract it without destroying the invoice history.
            if Decimal(sale.balance or 0) > 0:
                sale.balance = max(Decimal(sale.balance or 0) - total, Decimal('0'))
            _audit(company_id, user_id, 'SALE_RETURN', f'Devolución #{operation.id} de venta #{sale.id} por RD$ {total}')
            db.session.commit()
            flash('Devolución registrada e inventario actualizado.', 'success')
            return redirect(url_for('backoffice_bp.returns'))
        except (ValueError, TypeError) as exc:
            db.session.rollback()
            flash(str(exc), 'danger')
    return render_template('backoffice/return_form.html', user=db.session.get(User, user_id), sale=sale, returned=returned)


@backoffice_bp.route('/receivables', methods=['GET'])
def receivables():
    company_id, user_id = _identity()
    sales = Sale.query.filter(Sale.company_id == company_id, Sale.status == 'COMPLETED', Sale.balance > 0).order_by(Sale.created_at.asc()).all()
    payments = CustomerPayment.query.filter_by(company_id=company_id).order_by(CustomerPayment.created_at.desc()).limit(100).all()
    total = sum((Decimal(s.balance or 0) for s in sales), Decimal('0'))
    return render_template('backoffice/receivables.html', user=db.session.get(User, user_id), sales=sales, payments=payments, total=total)


@backoffice_bp.post('/receivables/<int:sale_id>/payment')
def receive_payment(sale_id):
    company_id, user_id = _identity()
    sale = Sale.query.filter_by(id=sale_id, company_id=company_id, status='COMPLETED').with_for_update().first_or_404()
    try:
        amount = _money(request.form.get('amount'), 'El abono')
        balance = Decimal(sale.balance or 0)
        if amount > balance:
            raise ValueError('El abono no puede superar el balance pendiente.')
        payment = CustomerPayment(company_id=company_id, client_id=sale.client_id, sale_id=sale.id,
                                  user_id=user_id, amount=amount, method=(request.form.get('method') or 'CASH')[:30],
                                  reference=(request.form.get('reference') or '').strip()[:100] or None,
                                  notes=(request.form.get('notes') or '').strip()[:255] or None)
        sale.amount_paid = Decimal(sale.amount_paid or 0) + amount
        sale.balance = balance - amount
        db.session.add(payment)
        _audit(company_id, user_id, 'CUSTOMER_PAYMENT', f'Abono a venta #{sale.id} por RD$ {amount}')
        db.session.commit()
        flash('Abono registrado correctamente.', 'success')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'danger')
    return redirect(url_for('backoffice_bp.receivables'))


@backoffice_bp.route('/payables', methods=['GET', 'POST'])
def payables():
    company_id, user_id = _identity()
    if request.method == 'POST':
        try:
            supplier_id = int(request.form.get('supplier_id') or 0)
            supplier = Supplier.query.filter_by(id=supplier_id, company_id=company_id).first()
            if not supplier:
                raise ValueError('Proveedor inválido.')
            document = (request.form.get('document_number') or '').strip()
            if not document:
                raise ValueError('Indica el número del documento.')
            due_date = datetime.strptime(request.form['due_date'], '%Y-%m-%d').date() if request.form.get('due_date') else None
            purchase_order_id = int(request.form['purchase_order_id']) if request.form.get('purchase_order_id') else None
            if purchase_order_id and not PurchaseOrder.query.filter_by(id=purchase_order_id, company_id=company_id).first():
                raise ValueError('La orden de compra no pertenece a esta empresa.')
            bill = SupplierBill(company_id=company_id, supplier_id=supplier.id,
                                purchase_order_id=purchase_order_id,
                                document_number=document[:80], amount=_money(request.form.get('amount')),
                                due_date=due_date, notes=(request.form.get('notes') or '').strip()[:255] or None)
            db.session.add(bill)
            _audit(company_id, user_id, 'SUPPLIER_BILL', f'Cuenta por pagar {document}')
            db.session.commit()
            flash('Cuenta por pagar creada.', 'success')
        except (ValueError, TypeError) as exc:
            db.session.rollback()
            flash(str(exc), 'danger')
        return redirect(url_for('backoffice_bp.payables'))
    bills = SupplierBill.query.filter_by(company_id=company_id).order_by(SupplierBill.created_at.desc()).all()
    suppliers = Supplier.query.filter_by(company_id=company_id).order_by(Supplier.name).all()
    orders = PurchaseOrder.query.filter_by(company_id=company_id).order_by(PurchaseOrder.created_at.desc()).limit(100).all()
    total = sum((b.balance for b in bills if b.status != 'PAID'), Decimal('0'))
    return render_template('backoffice/payables.html', user=db.session.get(User, user_id), bills=bills,
                           suppliers=suppliers, orders=orders, total=total)


@backoffice_bp.post('/payables/<int:bill_id>/payment')
def pay_supplier(bill_id):
    company_id, user_id = _identity()
    bill = SupplierBill.query.filter_by(id=bill_id, company_id=company_id).with_for_update().first_or_404()
    try:
        amount = _money(request.form.get('amount'), 'El pago')
        if amount > bill.balance:
            raise ValueError('El pago no puede superar el balance pendiente.')
        db.session.add(SupplierPayment(company_id=company_id, bill_id=bill.id, user_id=user_id,
                                       amount=amount, method=(request.form.get('method') or 'TRANSFER')[:30],
                                       reference=(request.form.get('reference') or '').strip()[:100] or None))
        bill.paid_amount = Decimal(bill.paid_amount or 0) + amount
        bill.status = 'PAID' if bill.paid_amount >= bill.amount else 'PARTIAL'
        _audit(company_id, user_id, 'SUPPLIER_PAYMENT', f'Pago de cuenta {bill.document_number} por RD$ {amount}')
        db.session.commit()
        flash('Pago al proveedor registrado.', 'success')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'danger')
    return redirect(url_for('backoffice_bp.payables'))


@backoffice_bp.route('/expenses', methods=['GET', 'POST'])
def expenses():
    company_id, user_id = _identity()
    if request.method == 'POST':
        try:
            expense_date = datetime.strptime(request.form.get('expense_date') or '', '%Y-%m-%d').date()
            supplier_id = int(request.form['supplier_id']) if request.form.get('supplier_id') else None
            if supplier_id and not Supplier.query.filter_by(id=supplier_id, company_id=company_id).first():
                raise ValueError('El proveedor no pertenece a esta empresa.')
            expense = Expense(company_id=company_id, user_id=user_id,
                              supplier_id=supplier_id,
                              category=(request.form.get('category') or '').strip()[:80],
                              description=(request.form.get('description') or '').strip()[:255],
                              amount=_money(request.form.get('amount')),
                              payment_method=(request.form.get('payment_method') or 'CASH')[:30],
                              reference=(request.form.get('reference') or '').strip()[:100] or None,
                              expense_date=expense_date)
            if not expense.category or not expense.description:
                raise ValueError('Categoría y descripción son obligatorias.')
            db.session.add(expense)
            _audit(company_id, user_id, 'EXPENSE', f'Gasto {expense.description} por RD$ {expense.amount}')
            db.session.commit()
            flash('Gasto registrado.', 'success')
        except (ValueError, TypeError) as exc:
            db.session.rollback()
            flash(str(exc), 'danger')
        return redirect(url_for('backoffice_bp.expenses'))
    rows = Expense.query.filter_by(company_id=company_id).order_by(Expense.expense_date.desc(), Expense.id.desc()).limit(250).all()
    suppliers = Supplier.query.filter_by(company_id=company_id).order_by(Supplier.name).all()
    total = sum((Decimal(row.amount or 0) for row in rows), Decimal('0'))
    return render_template('backoffice/expenses.html', user=db.session.get(User, user_id), rows=rows, suppliers=suppliers, total=total, today=date.today())


@backoffice_bp.route('/inventory-counts', methods=['GET', 'POST'])
def inventory_counts():
    company_id, user_id = _identity()
    if request.method == 'POST':
        warehouse_id = int(request.form.get('warehouse_id') or 0)
        warehouse = Warehouse.query.filter_by(id=warehouse_id, company_id=company_id).first_or_404()
        location_id = int(request.form['location_id']) if request.form.get('location_id') else None
        location = None
        if location_id:
            location = WarehouseLocation.query.filter_by(id=location_id, warehouse_id=warehouse.id, company_id=company_id).first_or_404()
        count = InventoryCount(company_id=company_id, warehouse_id=warehouse.id, location_id=location_id,
                               created_by=user_id, notes=(request.form.get('notes') or '').strip()[:255] or None)
        if location:
            rows = LocationStock.query.filter_by(company_id=company_id, location_id=location.id).all()
        else:
            rows = WarehouseStock.query.filter_by(company_id=company_id, warehouse_id=warehouse.id).all()
        current = {row.product_id: int(row.quantity or 0) for row in rows}
        products = Product.query.filter(Product.company_id == company_id, Product.status.is_(True),
                                        Product.product_type != ProductType.SERVICE).order_by(Product.name).all()
        for product in products:
            count.items.append(InventoryCountItem(product_id=product.id, expected_quantity=current.get(product.id, 0)))
        db.session.add(count)
        db.session.commit()
        flash('Conteo creado. Ahora registra las cantidades físicas.', 'success')
        return redirect(url_for('backoffice_bp.inventory_count_detail', count_id=count.id))
    rows = InventoryCount.query.filter_by(company_id=company_id).order_by(InventoryCount.created_at.desc()).all()
    warehouses = Warehouse.query.filter_by(company_id=company_id).order_by(Warehouse.name).all()
    locations = WarehouseLocation.query.filter_by(company_id=company_id, status=True).order_by(WarehouseLocation.name).all()
    return render_template('backoffice/inventory_counts.html', user=db.session.get(User, user_id), rows=rows,
                           warehouses=warehouses, locations=locations)


@backoffice_bp.route('/inventory-counts/<int:count_id>', methods=['GET', 'POST'])
def inventory_count_detail(count_id):
    company_id, user_id = _identity()
    count = InventoryCount.query.filter_by(id=count_id, company_id=company_id).first_or_404()
    if request.method == 'POST' and count.status == 'DRAFT':
        for item in count.items:
            raw = request.form.get(f'quantity_{item.id}')
            if raw not in (None, ''):
                value = int(raw)
                if value < 0:
                    flash('Las cantidades no pueden ser negativas.', 'danger')
                    return redirect(request.url)
                item.counted_quantity = value
        db.session.commit()
        flash('Conteo guardado.', 'success')
        return redirect(request.url)
    return render_template('backoffice/inventory_count_detail.html', user=db.session.get(User, user_id), count=count)


@backoffice_bp.post('/inventory-counts/<int:count_id>/approve')
def approve_inventory_count(count_id):
    company_id, user_id = _identity()
    count = InventoryCount.query.filter_by(id=count_id, company_id=company_id, status='DRAFT').with_for_update().first_or_404()
    if any(item.counted_quantity is None for item in count.items):
        flash('Completa todas las cantidades antes de aprobar.', 'warning')
        return redirect(url_for('backoffice_bp.inventory_count_detail', count_id=count.id))
    for item in count.items:
        difference = item.difference
        if count.location_id:
            location_stock = LocationStock.query.filter_by(company_id=company_id, location_id=count.location_id,
                                                           product_id=item.product_id).with_for_update().first()
            if not location_stock:
                location_stock = LocationStock(company_id=company_id, location_id=count.location_id,
                                               product_id=item.product_id, quantity=0)
                db.session.add(location_stock)
            location_stock.quantity = item.counted_quantity
        warehouse_stock = WarehouseStock.query.filter_by(company_id=company_id, warehouse_id=count.warehouse_id,
                                                         product_id=item.product_id).with_for_update().first()
        if not warehouse_stock:
            warehouse_stock = WarehouseStock(company_id=company_id, warehouse_id=count.warehouse_id,
                                             product_id=item.product_id, quantity=0)
            db.session.add(warehouse_stock)
        new_warehouse_quantity = int(warehouse_stock.quantity or 0) + difference if count.location_id else item.counted_quantity
        if new_warehouse_quantity < 0:
            db.session.rollback()
            flash(f'El ajuste de {item.product.name} produciría stock negativo en el almacén.', 'danger')
            return redirect(url_for('backoffice_bp.inventory_count_detail', count_id=count.id))
        warehouse_stock.quantity = new_warehouse_quantity
        if difference:
            db.session.add(StockMovement(company_id=company_id, warehouse_id=count.warehouse_id,
                                         product_id=item.product_id, movement_type='IN' if difference > 0 else 'OUT',
                                         quantity=abs(difference), reason=f'Ajuste conteo físico #{count.id}'))
    count.status = 'APPROVED'
    count.approved_by = user_id
    count.approved_at = datetime.utcnow()
    _audit(company_id, user_id, 'INVENTORY_COUNT_APPROVED', f'Conteo físico #{count.id} aprobado')
    db.session.commit()
    flash('Conteo aprobado y existencias conciliadas.', 'success')
    return redirect(url_for('backoffice_bp.inventory_count_detail', count_id=count.id))


@backoffice_bp.get('/notifications')
def notifications():
    company_id, user_id = _identity()
    refresh_system_notifications(company_id)
    rows = AppNotification.query.filter(
        AppNotification.company_id == company_id,
        or_(AppNotification.user_id.is_(None), AppNotification.user_id == user_id),
    ).order_by(AppNotification.read_at.is_(None).desc(), AppNotification.created_at.desc()).limit(200).all()
    unread = sum(1 for row in rows if not row.read_at)
    danger = sum(1 for row in rows if not row.read_at and row.level == 'DANGER')
    warning = sum(1 for row in rows if not row.read_at and row.level == 'WARNING')
    return render_template('backoffice/notifications.html', user=db.session.get(User, user_id), rows=rows,
                           unread=unread, danger=danger, warning=warning)


@backoffice_bp.post('/notifications/read-all')
def notifications_read_all():
    company_id, user_id = _identity()
    AppNotification.query.filter(
        AppNotification.company_id == company_id, AppNotification.read_at.is_(None),
        or_(AppNotification.user_id.is_(None), AppNotification.user_id == user_id),
    ).update({'read_at': datetime.utcnow()}, synchronize_session=False)
    db.session.commit()
    return redirect(url_for('backoffice_bp.notifications'))


@backoffice_bp.post('/notifications/<int:notification_id>/open')
def notification_open(notification_id):
    company_id, user_id = _identity()
    row = AppNotification.query.filter(
        AppNotification.id == notification_id,
        AppNotification.company_id == company_id,
        or_(AppNotification.user_id.is_(None), AppNotification.user_id == user_id),
    ).first_or_404()
    row.read_at = row.read_at or datetime.utcnow()
    db.session.commit()
    target = row.link or url_for('backoffice_bp.notifications')
    if not target.startswith('/') or target.startswith('//'):
        target = url_for('backoffice_bp.notifications')
    return redirect(target)


@backoffice_bp.route('/security', methods=['GET', 'POST'])
def security_settings():
    company_id, user_id = _identity()
    user = db.session.get(User, user_id)
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'prepare':
            user.totp_secret = generate_totp_secret()
            user.two_factor_enabled = False
            db.session.commit()
            flash('Clave preparada. Confírmala con un código de tu aplicación.', 'info')
        elif action == 'enable':
            if not user.totp_secret or not verify_totp(user.totp_secret, request.form.get('code')):
                flash('Código inválido o vencido.', 'danger')
                return redirect(request.url)
            user.two_factor_enabled = True
            _audit(company_id, user_id, 'TWO_FACTOR_ENABLED', 'Autenticación de dos factores activada')
            db.session.commit()
            flash('Autenticación de dos factores activada.', 'success')
        elif action == 'disable':
            if not user.check_password(request.form.get('password') or ''):
                flash('Contraseña incorrecta.', 'danger')
                return redirect(request.url)
            user.two_factor_enabled = False
            user.totp_secret = None
            _audit(company_id, user_id, 'TWO_FACTOR_DISABLED', 'Autenticación de dos factores desactivada')
            db.session.commit()
            flash('Autenticación de dos factores desactivada.', 'success')
        return redirect(request.url)
    issuer = 'OrbisERP'
    account = user.email
    otp_uri = f'otpauth://totp/{issuer}:{account}?secret={user.totp_secret}&issuer={issuer}&digits=6&period=30' if user.totp_secret else None
    return render_template('backoffice/security.html', user=user, otp_uri=otp_uri)
