from services.time_utils import utcnow
from datetime import date, datetime, timedelta
import re
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
from security import generate_recovery_codes, generate_totp_secret, store_recovery_codes, verify_totp
from services.validation import BusinessRuleError, positive_money, tenant_id
from services.quantity import as_decimal, base_quantity_from_factor, product_quantity
from models.retail import (
    WarehouseVariantStock, InventorySerial, InventoryLot, InventoryConditionStock, Branch,
    SaleItemLotAllocation, SaleReturnItemLotAllocation, SaleReturnItemSerial,
    InventorySerialEvent,
)


backoffice_bp = Blueprint('backoffice_bp', __name__, url_prefix='/backoffice')


def _identity():
    company_id = session.get('company_id')
    user_id = session.get('user_id')
    if not company_id or not user_id:
        abort(401)
    return int(company_id), int(user_id)


def _money(raw, field='Monto'):
    return positive_money(raw, field)


def _optional_tenant_id(raw, field):
    if raw is None or not str(raw).strip():
        return None
    return tenant_id(raw, field)


def _audit(company_id, user_id, action, description):
    db.session.add(AuditLog(
        company_id=company_id, user_id=user_id, action=action,
        description=description[:1000], ip_address=(request.remote_addr or '')[:50],
    ))


def _restore_available_stock(company_id, item, base_qty, sale_id):
    """Return sellable quantity to the same warehouse/variant used by the sale."""
    if not item.warehouse_id or item.product.product_type == ProductType.SERVICE:
        return
    stock = WarehouseStock.query.filter_by(
        company_id=company_id, warehouse_id=item.warehouse_id, product_id=item.product_id,
    ).with_for_update().first()
    if not stock:
        stock = WarehouseStock(
            company_id=company_id, warehouse_id=item.warehouse_id,
            product_id=item.product_id, quantity=0,
        )
        db.session.add(stock)
    stock.quantity = as_decimal(stock.quantity) + base_qty
    if item.variant_id:
        variant_stock = WarehouseVariantStock.query.filter_by(
            company_id=company_id, warehouse_id=item.warehouse_id, variant_id=item.variant_id,
        ).with_for_update().first()
        if not variant_stock:
            variant_stock = WarehouseVariantStock(
                company_id=company_id, warehouse_id=item.warehouse_id,
                product_id=item.product_id, variant_id=item.variant_id, quantity=0,
            )
            db.session.add(variant_stock)
        variant_stock.quantity = as_decimal(variant_stock.quantity) + base_qty
    db.session.add(StockMovement(
        company_id=company_id, user_id=session.get('user_id'), warehouse_id=item.warehouse_id, product_id=item.product_id,
        movement_type='IN', quantity=base_qty, reason=f'Devolución venta #{sale_id}',
    ))


def _add_condition_stock(company_id, item, base_qty, condition, sale_id):
    """Register a physical return that is not sellable yet.

    Condition stock is deliberately separated from WarehouseStock. The movement
    ledger still receives an IN entry so the physical arrival is auditable,
    while availability reports continue to exclude quarantine/damaged units.
    """
    if not item.warehouse_id or item.product.product_type == ProductType.SERVICE:
        return
    row = InventoryConditionStock.query.filter_by(
        company_id=company_id, warehouse_id=item.warehouse_id,
        product_id=item.product_id, variant_id=item.variant_id, condition=condition,
    ).with_for_update().first()
    if not row:
        row = InventoryConditionStock(
            company_id=company_id, warehouse_id=item.warehouse_id,
            product_id=item.product_id, variant_id=item.variant_id,
            condition=condition, quantity=0,
        )
        db.session.add(row)
    row.quantity = as_decimal(row.quantity) + base_qty
    label = 'Cuarentena' if condition == 'QUARANTINE' else 'Dañado'
    db.session.add(StockMovement(
        company_id=company_id,
        user_id=session.get('user_id'),
        warehouse_id=item.warehouse_id,
        product_id=item.product_id,
        movement_type='IN',
        quantity=base_qty,
        reason=f'Devolución venta #{sale_id} -> {label}',
    ))


def _restore_lot_trace(company_id, sale_item, return_item, base_qty, disposition):
    """Map a partial return back to the exact lots allocated on the original sale."""
    allocations = SaleItemLotAllocation.query.filter_by(
        company_id=company_id, sale_item_id=sale_item.id,
    ).order_by(SaleItemLotAllocation.id.asc()).all()
    if not allocations:
        raise BusinessRuleError(
            f'La venta de {sale_item.product.name} no conserva asignación de lote; '
            'no es seguro reintegrarla automáticamente.'
        )
    prior_rows = db.session.query(
        SaleReturnItemLotAllocation.lot_id,
        func.coalesce(func.sum(SaleReturnItemLotAllocation.quantity), 0),
    ).filter(
        SaleReturnItemLotAllocation.company_id == company_id,
        SaleReturnItemLotAllocation.sale_item_id == sale_item.id,
    ).group_by(SaleReturnItemLotAllocation.lot_id).all()
    prior = {lot_id: as_decimal(qty) for lot_id, qty in prior_rows}
    remaining = as_decimal(base_qty)
    for allocation in allocations:
        if remaining <= 0:
            break
        available = max(as_decimal(allocation.quantity) - prior.get(allocation.lot_id, Decimal('0')), Decimal('0'))
        if available <= 0:
            continue
        used = min(available, remaining)
        lot = InventoryLot.query.filter_by(id=allocation.lot_id, company_id=company_id).with_for_update().first()
        if not lot:
            raise BusinessRuleError('No se encontró uno de los lotes originales de la venta.')
        if disposition == 'AVAILABLE' and lot.expires_at and lot.expires_at < date.today():
            raise BusinessRuleError(
                f'El lote {lot.lot_number} está vencido; devuélvelo a Cuarentena o Dañado, no a Disponible.'
            )
        db.session.add(SaleReturnItemLotAllocation(
            company_id=company_id, return_item_id=return_item.id, sale_item_id=sale_item.id,
            lot_id=lot.id, quantity=used, disposition=disposition,
        ))
        if disposition == 'AVAILABLE':
            lot.quantity = as_decimal(lot.quantity) + used
            lot.status = 'AVAILABLE'
        remaining -= used
    if remaining > 0:
        raise BusinessRuleError(
            f'La cantidad devuelta de {sale_item.product.name} supera la trazabilidad de lotes disponible.'
        )


def _restore_serial_trace(company_id, sale_item, return_item, base_qty, disposition, selected_ids):
    required = as_decimal(base_qty)
    if required != required.to_integral_value():
        raise BusinessRuleError('Un producto serializado solo puede devolverse en unidades enteras.')
    expected = int(required)
    selected_ids = [int(value) for value in selected_ids if str(value).isdigit()]
    if len(set(selected_ids)) != expected:
        raise BusinessRuleError(
            f'Selecciona exactamente {expected} serial(es)/IMEI para {sale_item.product.name}.'
        )
    previously_returned = {
        row.serial_id for row in SaleReturnItemSerial.query.filter_by(
            company_id=company_id, sale_item_id=sale_item.id,
        ).all()
    }
    rows = InventorySerial.query.filter(
        InventorySerial.company_id == company_id,
        InventorySerial.id.in_(selected_ids),
        InventorySerial.product_id == sale_item.product_id,
    ).with_for_update().all()
    if len(rows) != expected:
        raise BusinessRuleError('Uno o más seriales seleccionados no pertenecen a esta empresa/producto.')
    for serial in rows:
        if serial.id in previously_returned:
            raise BusinessRuleError(f'El serial {serial.serial_number} ya fue devuelto anteriormente.')
        sold_here = serial.sale_item_id == sale_item.id or InventorySerialEvent.query.filter_by(
            company_id=company_id, serial_id=serial.id, sale_item_id=sale_item.id, event_type='SOLD'
        ).first() is not None
        if not sold_here:
            raise BusinessRuleError(f'El serial {serial.serial_number} no pertenece a esta venta.')
        db.session.add(SaleReturnItemSerial(
            company_id=company_id, return_item_id=return_item.id, sale_item_id=sale_item.id,
            serial_id=serial.id, disposition=disposition,
        ))
        if disposition == 'AVAILABLE':
            serial.status = 'AVAILABLE'
            serial.sale_item_id = None
            serial.warehouse_id = sale_item.warehouse_id
        elif disposition == 'QUARANTINE':
            serial.status = 'QUARANTINE'
            serial.sale_item_id = None
            serial.warehouse_id = sale_item.warehouse_id
        elif disposition == 'DAMAGED':
            serial.status = 'SCRAPPED'
            serial.sale_item_id = None
            serial.warehouse_id = sale_item.warehouse_id
        db.session.add(InventorySerialEvent(
            company_id=company_id, serial_id=serial.id, event_type='RETURNED',
            sale_item_id=sale_item.id, return_item_id=return_item.id,
            warehouse_id=sale_item.warehouse_id,
            notes=f'Devolución · destino {disposition}',
        ))


def refresh_system_notifications(company_id):
    """Evaluate the configurable notification rules used by the workspace."""
    from services.notification_rules import evaluate_notification_rules
    return evaluate_notification_rules(company_id)


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
    rows = SaleReturn.query.filter_by(company_id=company_id).order_by(SaleReturn.created_at.desc()).limit(250).all()
    sale_ref = (request.args.get('sale') or '').strip()
    selected_sale = None
    selected_returned = Decimal('0')
    if sale_ref:
        # Operators commonly type #123, VEN-000123 or simply 123. Only the
        # numeric sale id is trusted and tenant/status filters always apply.
        match = re.fullmatch(r'(?:#|VENTA[- ]?|VEN[- ]?)?0*(\d+)', sale_ref, flags=re.IGNORECASE)
        if not match:
            flash('Número de venta no válido. Escribe, por ejemplo, 125, #125 o VEN-000125.', 'danger')
        else:
            sale_id = int(match.group(1))
            selected_sale = Sale.query.filter_by(
                id=sale_id, company_id=company_id, status='COMPLETED'
            ).first()
            if not selected_sale:
                flash(
                    f'No encontramos una venta completada #{sale_id} en esta empresa. '
                    'Verifica el número antes de iniciar la devolución.',
                    'danger',
                )
            else:
                selected_returned = db.session.query(func.coalesce(func.sum(SaleReturn.total_refund), 0)).filter(
                    SaleReturn.company_id == company_id,
                    SaleReturn.sale_id == selected_sale.id,
                    SaleReturn.status == 'COMPLETED',
                ).scalar() or Decimal('0')
    return render_template(
        'backoffice/returns.html',
        user=db.session.get(User, user_id),
        rows=rows,
        sale_ref=sale_ref,
        selected_sale=selected_sale,
        selected_returned=selected_returned,
    )


@backoffice_bp.route('/returns/new/<int:sale_id>', methods=['GET', 'POST'])
def create_return(sale_id):
    company_id, user_id = _identity()
    sale = Sale.query.filter_by(
        id=sale_id, company_id=company_id, status='COMPLETED'
    ).with_for_update().first_or_404()
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
                               restocked=False)
        db.session.add(operation)
        total = Decimal('0')
        selected = 0
        any_available_restock = False
        try:
            for item in sale.items:
                qty = product_quantity(
                    request.form.get(f'quantity_{item.id}', 0) or 0,
                    f'Cantidad de {item.product.name}',
                    product=item.product, uom=item.uom, allow_zero=True,
                )
                available = as_decimal(item.quantity) - as_decimal(returned.get(item.id, 0) or 0)
                if qty < 0 or qty > available:
                    raise ValueError(f'Cantidad inválida para {item.product.name}.')
                if not qty:
                    continue
                selected += 1
                total += Decimal(item.price) * qty
                disposition = (request.form.get(f'disposition_{item.id}') or 'AVAILABLE').upper()
                if disposition not in {'AVAILABLE', 'QUARANTINE', 'DAMAGED', 'NONE'}:
                    raise BusinessRuleError(f'Destino de devolución inválido para {item.product.name}.')
                return_item = SaleReturnItem(
                    sale_item_id=item.id, product_id=item.product_id, warehouse_id=item.warehouse_id,
                    quantity=qty, unit_price=item.price, variant_id=item.variant_id, uom_id=item.uom_id, uom_factor=item.uom_factor,
                    disposition=disposition,
                )
                operation.items.append(return_item)
                db.session.flush()
                base_qty = base_quantity_from_factor(qty, item.uom_factor or 1, f'Cantidad base de {item.product.name}')

                tracking = getattr(item.product, 'tracking', 'NONE') or 'NONE'
                if tracking == 'LOT':
                    _restore_lot_trace(company_id, item, return_item, base_qty, disposition)
                elif tracking == 'SERIAL':
                    _restore_serial_trace(
                        company_id, item, return_item, base_qty, disposition,
                        request.form.getlist(f'serial_{item.id}'),
                    )

                if item.product.product_type != ProductType.SERVICE:
                    if disposition == 'AVAILABLE':
                        _restore_available_stock(company_id, item, base_qty, sale.id)
                        any_available_restock = True
                    elif disposition in {'QUARANTINE', 'DAMAGED'}:
                        _add_condition_stock(company_id, item, base_qty, disposition, sale.id)
            if not selected:
                raise ValueError('Selecciona al menos un producto.')
            operation.total_refund = total
            operation.restocked = any_available_restock
            db.session.flush()
            # Keep the sale as COMPLETED: the return is an immutable linked
            # operation and reports subtract it without destroying the invoice history.
            if Decimal(sale.balance or 0) > 0:
                sale.balance = max(Decimal(sale.balance or 0) - total, Decimal('0'))
            _audit(company_id, user_id, 'SALE_RETURN', f'Devolución #{operation.id} de venta #{sale.id} por RD$ {total}')
            db.session.commit()
            flash('Devolución registrada. El reembolso, la trazabilidad y el movimiento de inventario quedaron vinculados a la venta original.', 'success')
            return redirect(url_for('backoffice_bp.returns'))
        except (BusinessRuleError, ValueError, TypeError) as exc:
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
            supplier_id = tenant_id(request.form.get('supplier_id'), 'Proveedor')
            supplier = Supplier.query.filter_by(id=supplier_id, company_id=company_id).filter(Supplier.archived_at.is_(None)).first()
            if not supplier:
                raise ValueError('Proveedor inválido.')
            document = (request.form.get('document_number') or '').strip()
            if not document:
                raise ValueError('Indica el número del documento.')
            due_date = datetime.strptime(request.form['due_date'], '%Y-%m-%d').date() if request.form.get('due_date') else None
            purchase_order_id = _optional_tenant_id(request.form.get('purchase_order_id'), 'Orden de compra')
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
    suppliers = Supplier.query.filter_by(company_id=company_id).filter(Supplier.archived_at.is_(None)).order_by(Supplier.name).all()
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
    operator = db.session.get(User, user_id)
    branches = Branch.query.filter_by(company_id=company_id, status=True).order_by(Branch.is_main.desc(), Branch.name.asc()).all()
    branch_locked = bool(operator and operator.role not in {'admin', 'superadmin'} and operator.branch_id)
    requested_branch_id = request.values.get('branch_id', type=int)
    default_branch_id = (
        operator.branch_id if branch_locked else
        requested_branch_id or session.get('cash_branch_id') or (operator.branch_id if operator else None)
    )
    selected_branch = next((branch for branch in branches if branch.id == default_branch_id), None)
    if not selected_branch and branches:
        selected_branch = branches[0]

    if request.method == 'POST':
        try:
            if not selected_branch:
                raise ValueError('No hay una sucursal activa para registrar este gasto. Configura una sucursal primero.')
            expense_date = datetime.strptime(request.form.get('expense_date') or '', '%Y-%m-%d').date()
            supplier_id = _optional_tenant_id(request.form.get('supplier_id'), 'Proveedor')
            if supplier_id and not Supplier.query.filter_by(id=supplier_id, company_id=company_id).filter(Supplier.archived_at.is_(None)).first():
                raise ValueError('El proveedor no pertenece a esta empresa.')
            expense = Expense(company_id=company_id, user_id=user_id,
                              branch_id=selected_branch.id,
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
            _audit(company_id, user_id, 'EXPENSE', f'Gasto {expense.description} por RD$ {expense.amount} · {selected_branch.name}')
            db.session.commit()
            flash(f'Gasto registrado en {selected_branch.name}. Si fue en efectivo, afectará únicamente el arqueo de esa sucursal.', 'success')
        except (ValueError, TypeError) as exc:
            db.session.rollback()
            flash(str(exc), 'danger')
        return redirect(url_for('backoffice_bp.expenses', branch_id=(selected_branch.id if selected_branch else None)))
    rows_query = Expense.query.filter_by(company_id=company_id)
    if selected_branch:
        rows_query = rows_query.filter(Expense.branch_id == selected_branch.id)
    rows = rows_query.order_by(Expense.expense_date.desc(), Expense.id.desc()).limit(250).all()
    suppliers = Supplier.query.filter_by(company_id=company_id).filter(Supplier.archived_at.is_(None)).order_by(Supplier.name).all()
    total = sum((Decimal(row.amount or 0) for row in rows), Decimal('0'))
    return render_template('backoffice/expenses.html', user=operator, rows=rows, suppliers=suppliers, total=total, today=date.today(), branches=branches, selected_branch=selected_branch, branch_locked=branch_locked)


@backoffice_bp.route('/inventory-counts', methods=['GET', 'POST'])
def inventory_counts():
    company_id, user_id = _identity()
    if request.method == 'POST':
        try:
            warehouse_id = tenant_id(request.form.get('warehouse_id'), 'Almacén')
            warehouse = Warehouse.query.filter_by(id=warehouse_id, company_id=company_id).first()
            if not warehouse:
                raise BusinessRuleError('El almacén seleccionado no pertenece a esta empresa.')
            location_id = _optional_tenant_id(request.form.get('location_id'), 'Ubicación')
            location = None
            if location_id:
                location = WarehouseLocation.query.filter_by(
                    id=location_id, warehouse_id=warehouse.id, company_id=company_id, status=True,
                ).first()
                if not location:
                    raise BusinessRuleError('La ubicación seleccionada no pertenece al almacén.')
            count = InventoryCount(company_id=company_id, warehouse_id=warehouse.id, location_id=location_id,
                                   created_by=user_id, notes=(request.form.get('notes') or '').strip()[:255] or None)
            if location:
                rows = LocationStock.query.filter_by(company_id=company_id, location_id=location.id).all()
            else:
                rows = WarehouseStock.query.filter_by(company_id=company_id, warehouse_id=warehouse.id).all()
            current = {row.product_id: as_decimal(row.quantity) for row in rows}
            products = Product.query.filter(Product.company_id == company_id, Product.status.is_(True), Product.archived_at.is_(None),
                                            Product.product_type != ProductType.SERVICE).order_by(Product.name).all()
            for product in products:
                count.items.append(InventoryCountItem(product_id=product.id, expected_quantity=current.get(product.id, 0)))
            db.session.add(count)
            db.session.commit()
        except BusinessRuleError as exc:
            db.session.rollback()
            flash(str(exc), 'danger')
            return redirect(url_for('backoffice_bp.inventory_counts'))
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
                try:
                    value = product_quantity(raw, 'Cantidad contada', product=item.product, uom=item.product.base_uom, allow_zero=True)
                except BusinessRuleError as exc:
                    flash(str(exc), 'danger')
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
        new_warehouse_quantity = as_decimal(warehouse_stock.quantity) + as_decimal(difference) if count.location_id else as_decimal(item.counted_quantity)
        if new_warehouse_quantity < 0:
            db.session.rollback()
            flash(f'El ajuste de {item.product.name} produciría stock negativo en el almacén.', 'danger')
            return redirect(url_for('backoffice_bp.inventory_count_detail', count_id=count.id))
        warehouse_stock.quantity = new_warehouse_quantity
        if difference:
            db.session.add(StockMovement(company_id=company_id, user_id=session.get('user_id'), warehouse_id=count.warehouse_id,
                                         product_id=item.product_id, movement_type='IN' if difference > 0 else 'OUT',
                                         quantity=abs(difference), reason=f'Ajuste conteo físico #{count.id}'))
    count.status = 'APPROVED'
    count.approved_by = user_id
    count.approved_at = utcnow()
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
    ).update({'read_at': utcnow()}, synchronize_session=False)
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
    row.read_at = row.read_at or utcnow()
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
            recovery_codes = generate_recovery_codes()
            store_recovery_codes(user, recovery_codes)
            session['new_recovery_codes'] = recovery_codes
            _audit(company_id, user_id, 'TWO_FACTOR_ENABLED', 'Autenticación de dos factores activada')
            db.session.commit()
            flash('Autenticación de dos factores activada.', 'success')
        elif action == 'disable':
            if not user.check_password(request.form.get('password') or ''):
                flash('Contraseña incorrecta.', 'danger')
                return redirect(request.url)
            user.two_factor_enabled = False
            user.totp_secret = None
            user.totp_recovery_codes = None
            _audit(company_id, user_id, 'TWO_FACTOR_DISABLED', 'Autenticación de dos factores desactivada')
            db.session.commit()
            flash('Autenticación de dos factores desactivada.', 'success')
        elif action == 'regenerate':
            if not user.check_password(request.form.get('password') or ''):
                flash('Contraseña incorrecta.', 'danger')
                return redirect(request.url)
            if not verify_totp(user.totp_secret, request.form.get('code')):
                flash('Código temporal inválido o vencido.', 'danger')
                return redirect(request.url)
            recovery_codes = generate_recovery_codes()
            store_recovery_codes(user, recovery_codes)
            session['new_recovery_codes'] = recovery_codes
            _audit(company_id, user_id, 'TWO_FACTOR_RECOVERY_REGENERATED', 'Códigos de recuperación regenerados')
            db.session.commit()
            flash('Códigos regenerados. Los anteriores quedaron invalidados.', 'success')
        return redirect(request.url)
    issuer = 'OrbisERP'
    account = user.email
    otp_uri = f'otpauth://totp/{issuer}:{account}?secret={user.totp_secret}&issuer={issuer}&digits=6&period=30' if user.totp_secret else None
    return render_template(
        'backoffice/security.html', user=user, otp_uri=otp_uri,
        recovery_codes=session.pop('new_recovery_codes', None),
    )
