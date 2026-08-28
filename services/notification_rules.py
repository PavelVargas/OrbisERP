from services.time_utils import utcnow
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func

from db import db
from models.backoffice import AppNotification, Expense, SupplierBill
from models.products.products import Product, ProductType
from models.purchase.purchase_order import PurchaseOrder
from models.crm.crm import Task
from models.client.client import Client
from models.productivity import NotificationRule
from models.sales.sales import Sale
from models.warehouse_stock.warehouse_stock import WarehouseStock


RULE_LABELS = {
    'STOCK_BELOW_MIN': 'Stock bajo',
    'STOCK_OUT': 'Producto agotado',
    'RECEIVABLE_OVERDUE': 'Cobros vencidos',
    'RECEIVABLE_AMOUNT_ABOVE': 'Saldo por cobrar alto',
    'PAYABLE_DUE': 'Pagos próximos',
    'PAYABLE_OVERDUE': 'Pagos vencidos',
    'EXPENSE_AMOUNT_ABOVE': 'Gasto elevado',
    'SALE_AMOUNT_ABOVE': 'Venta de importe alto',
    'CUSTOM': 'Alerta personalizada',
}

RULE_DESCRIPTIONS = {
    'STOCK_BELOW_MIN': 'Avisa cuando una referencia llega a su mínimo o al umbral definido.',
    'STOCK_OUT': 'Avisa inmediatamente cuando una referencia inventariable llega a cero.',
    'RECEIVABLE_OVERDUE': 'Avisa cuando una venta con saldo supera los días configurados.',
    'RECEIVABLE_AMOUNT_ABOVE': 'Avisa cuando el saldo de una venta supera el importe configurado.',
    'PAYABLE_DUE': 'Avisa con anticipación cuando una cuenta por pagar se acerca a su fecha límite.',
    'PAYABLE_OVERDUE': 'Avisa cuando una cuenta por pagar ya está vencida.',
    'EXPENSE_AMOUNT_ABOVE': 'Avisa sobre gastos recientes por encima del importe configurado.',
    'SALE_AMOUNT_ABOVE': 'Avisa sobre ventas recientes por encima del importe configurado.',
    'CUSTOM': 'Evalúa una fuente operativa con el operador, umbral y mensaje que definas.',
}

CUSTOM_SOURCES = {
    'STOCK': {'label': 'Existencia de producto', 'link': '/stock', 'unit': 'unidades'},
    'SALE': {'label': 'Total de venta', 'link': '/sales', 'unit': 'importe'},
    'RECEIVABLE': {'label': 'Saldo por cobrar', 'link': '/backoffice/receivables', 'unit': 'importe'},
    'PAYABLE': {'label': 'Saldo por pagar', 'link': '/backoffice/payables', 'unit': 'importe'},
    'EXPENSE': {'label': 'Importe de gasto', 'link': '/backoffice/expenses', 'unit': 'importe'},
    'PURCHASE': {'label': 'Total de orden de compra', 'link': '/purchase', 'unit': 'importe'},
    'CRM_TASK': {'label': 'Días vencidos de tarea CRM', 'link': '/crm', 'unit': 'días'},
}

OPERATORS = {
    'LT': '<',
    'LTE': '≤',
    'EQ': '=',
    'GTE': '≥',
    'GT': '>',
}

DEFAULT_RULES = (
    ('STOCK_BELOW_MIN', 0, 'WARNING'),
    ('STOCK_OUT', 0, 'DANGER'),
    ('RECEIVABLE_OVERDUE', 15, 'WARNING'),
    ('PAYABLE_DUE', 3, 'WARNING'),
    ('PAYABLE_OVERDUE', 0, 'DANGER'),
)


def ensure_default_rules(company_id):
    rules = NotificationRule.query.filter_by(company_id=company_id).order_by(NotificationRule.id).all()
    existing = {r.rule_type for r in rules if r.rule_type != 'CUSTOM'}
    changed = False
    for rule_type, threshold, level in DEFAULT_RULES:
        if rule_type not in existing:
            db.session.add(NotificationRule(
                company_id=company_id,
                rule_type=rule_type,
                name=RULE_LABELS[rule_type],
                threshold=threshold,
                level=level,
                enabled=True,
            ))
            changed = True
    for rule in rules:
        if not rule.name:
            rule.name = RULE_LABELS.get(rule.rule_type, rule.rule_type.replace('_', ' ').title())
            changed = True
    if changed:
        db.session.commit()
    return NotificationRule.query.filter_by(company_id=company_id).order_by(
        (NotificationRule.rule_type == 'CUSTOM').asc(), NotificationRule.id.asc()
    ).all()


def _upsert_notification(company_id, *, key, title, message, link, level='WARNING', user_id=None):
    row = AppNotification.query.filter_by(company_id=company_id, dedupe_key=key).first()
    if row:
        row.title = title[:120]
        row.message = message[:255]
        row.link = link
        row.level = level
        row.user_id = user_id
        if row.read_at and row.created_at < utcnow() - timedelta(days=1):
            row.read_at = None
            row.created_at = utcnow()
        return row
    row = AppNotification(
        company_id=company_id,
        user_id=user_id,
        level=level,
        title=title[:120],
        message=message[:255],
        link=link,
        dedupe_key=key,
    )
    db.session.add(row)
    return row


def _matches(operator, value, threshold):
    value = Decimal(str(value or 0))
    threshold = Decimal(str(threshold or 0))
    return {
        'LT': value < threshold,
        'LTE': value <= threshold,
        'EQ': value == threshold,
        'GTE': value >= threshold,
        'GT': value > threshold,
    }.get(operator or 'GTE', False)


def _render_custom_message(rule, **context):
    template = (rule.message or '').strip()
    fallback = '{name}: valor {value} cumple la condición {operator} {threshold}.'
    values = {
        'name': context.get('name', 'Registro'),
        'value': context.get('value', 0),
        'threshold': rule.threshold,
        'operator': OPERATORS.get(rule.operator or 'GTE', rule.operator or '>='),
        'id': context.get('id', ''),
    }
    try:
        return (template or fallback).format_map(values)[:255]
    except (KeyError, ValueError):
        return fallback.format_map(values)[:255]


def _custom_candidates(rule, company_id):
    source = (rule.custom_source or '').upper()
    lookback = max(int(rule.lookback_days or 0), 0)
    cutoff_dt = utcnow() - timedelta(days=lookback)
    cutoff_date = date.today() - timedelta(days=lookback)

    if source == 'STOCK':
        rows = db.session.query(
            Product.id, Product.name,
            func.coalesce(func.sum(WarehouseStock.quantity), 0).label('value'),
        ).outerjoin(
            WarehouseStock,
            (WarehouseStock.product_id == Product.id) & (WarehouseStock.company_id == company_id),
        ).filter(
            Product.company_id == company_id,
            Product.archived_at.is_(None),
            Product.status.is_(True),
            Product.product_type != ProductType.SERVICE,
        ).group_by(Product.id, Product.name).limit(250).all()
        return [(row.id, row.name, row.value, f'/product/{row.id}') for row in rows]

    if source == 'SALE':
        rows = Sale.query.filter(
            Sale.company_id == company_id,
            Sale.status == 'COMPLETED',
            Sale.created_at >= cutoff_dt,
        ).order_by(Sale.created_at.desc()).limit(250).all()
        return [(row.id, f'Venta #{row.id}', row.total or 0, f'/sales/{row.id}') for row in rows]

    if source == 'RECEIVABLE':
        rows = Sale.query.filter(
            Sale.company_id == company_id,
            Sale.status == 'COMPLETED',
            Sale.balance > 0,
        ).order_by(Sale.created_at.desc()).limit(250).all()
        return [(row.id, f'Venta #{row.id}', row.balance or 0, '/backoffice/receivables') for row in rows]

    if source == 'PAYABLE':
        rows = SupplierBill.query.filter(
            SupplierBill.company_id == company_id,
            SupplierBill.status != 'PAID',
        ).order_by(SupplierBill.created_at.desc()).limit(250).all()
        return [(row.id, row.document_number, row.balance, '/backoffice/payables') for row in rows]

    if source == 'EXPENSE':
        rows = Expense.query.filter(
            Expense.company_id == company_id,
            Expense.expense_date >= cutoff_date,
            Expense.status == 'POSTED',
        ).order_by(Expense.expense_date.desc()).limit(250).all()
        return [(row.id, row.description, row.amount or 0, '/backoffice/expenses') for row in rows]

    if source == 'PURCHASE':
        rows = PurchaseOrder.query.filter(
            PurchaseOrder.company_id == company_id,
            PurchaseOrder.created_at >= cutoff_dt,
        ).order_by(PurchaseOrder.created_at.desc()).limit(250).all()
        return [(row.id, f'Orden de compra #{row.id}', row.total_cost or 0, f'/purchase/{row.id}') for row in rows]

    if source == 'CRM_TASK':
        rows = db.session.query(Task, Client).join(Client, Client.id == Task.client_id).filter(
            Client.company_id == company_id,
            Client.archived_at.is_(None),
            Task.is_completed.is_(False),
        ).order_by(Task.due_date.asc()).limit(250).all()
        candidates = []
        for task, client in rows:
            due_date = task.due_date.date() if task.due_date else date.today()
            days_overdue = (date.today() - due_date).days
            candidates.append((task.id, f'{task.title} · {client.name}', days_overdue, f'/crm?client={client.id}'))
        return candidates

    return []


def _evaluate_custom(rule, company_id, active_keys):
    produced = 0
    default_link = CUSTOM_SOURCES.get((rule.custom_source or '').upper(), {}).get('link', '/backoffice/notifications')
    custom_link = rule.link if (rule.link or '').startswith('/') and not (rule.link or '').startswith('//') else None
    for entity_id, name, value, candidate_link in _custom_candidates(rule, company_id):
        if not _matches(rule.operator, value, rule.threshold):
            continue
        key = f'rule:{rule.id}:custom:{entity_id}'
        active_keys.add(key)
        _upsert_notification(
            company_id,
            key=key,
            title=rule.name or 'Alerta personalizada',
            message=_render_custom_message(rule, id=entity_id, name=name, value=value),
            link=custom_link or candidate_link or default_link,
            level=rule.level,
            user_id=rule.target_user_id,
        )
        produced += 1
    return produced


def evaluate_notification_rules(company_id):
    rules = ensure_default_rules(company_id)
    produced = 0
    active_keys = set()
    today = date.today()

    for rule in rules:
        if not rule.enabled:
            continue

        if rule.rule_type == 'STOCK_BELOW_MIN':
            rows = db.session.query(
                Product.id, Product.name, Product.sku, Product.min_stock,
                func.coalesce(func.sum(WarehouseStock.quantity), 0).label('stock'),
            ).outerjoin(
                WarehouseStock,
                (WarehouseStock.product_id == Product.id) & (WarehouseStock.company_id == company_id),
            ).filter(
                Product.company_id == company_id,
                Product.archived_at.is_(None), Product.status.is_(True),
                Product.product_type != ProductType.SERVICE,
            ).group_by(Product.id, Product.name, Product.sku, Product.min_stock).all()
            for product_id, name, sku, min_stock, stock in rows:
                threshold = max(Decimal(str(min_stock or 0)), Decimal(str(rule.threshold or 0)))
                current_stock = Decimal(str(stock or 0))
                if current_stock <= threshold:
                    key = f'rule:{rule.id}:stock:{product_id}'
                    active_keys.add(key)
                    _upsert_notification(
                        company_id, key=key, title=rule.name or 'Stock bajo',
                        message=f'{name} ({sku}) tiene {current_stock.normalize()} unidades; mínimo {threshold.normalize()}.',
                        link=f'/product/{product_id}', level=rule.level, user_id=rule.target_user_id,
                    )
                    produced += 1

        elif rule.rule_type == 'STOCK_OUT':
            rows = db.session.query(
                Product.id, Product.name, Product.sku,
                func.coalesce(func.sum(WarehouseStock.quantity), 0).label('stock'),
            ).outerjoin(
                WarehouseStock,
                (WarehouseStock.product_id == Product.id) & (WarehouseStock.company_id == company_id),
            ).filter(
                Product.company_id == company_id,
                Product.archived_at.is_(None), Product.status.is_(True),
                Product.product_type != ProductType.SERVICE,
            ).group_by(Product.id, Product.name, Product.sku).having(
                func.coalesce(func.sum(WarehouseStock.quantity), 0) <= 0
            ).all()
            for product_id, name, sku, _ in rows:
                key = f'rule:{rule.id}:out:{product_id}'
                active_keys.add(key)
                _upsert_notification(
                    company_id, key=key, title=rule.name or 'Producto agotado',
                    message=f'{name} ({sku}) no tiene unidades disponibles.',
                    link=f'/product/{product_id}', level=rule.level, user_id=rule.target_user_id,
                )
                produced += 1

        elif rule.rule_type == 'RECEIVABLE_OVERDUE':
            cutoff = utcnow() - timedelta(days=max(int(rule.threshold or 0), 0))
            sales = Sale.query.filter(
                Sale.company_id == company_id, Sale.status == 'COMPLETED',
                Sale.balance > 0, Sale.created_at <= cutoff,
            ).order_by(Sale.created_at.asc()).limit(150).all()
            for sale in sales:
                key = f'rule:{rule.id}:receivable:{sale.id}'
                active_keys.add(key)
                _upsert_notification(
                    company_id, key=key, title=rule.name or 'Cuenta por cobrar vencida',
                    message=f'Venta #{sale.id} mantiene un saldo de {sale.balance}.',
                    link='/backoffice/receivables', level=rule.level, user_id=rule.target_user_id,
                )
                produced += 1

        elif rule.rule_type == 'RECEIVABLE_AMOUNT_ABOVE':
            sales = Sale.query.filter(
                Sale.company_id == company_id, Sale.status == 'COMPLETED',
                Sale.balance > max(int(rule.threshold or 0), 0),
            ).order_by(Sale.balance.desc()).limit(150).all()
            for sale in sales:
                key = f'rule:{rule.id}:receivable-amount:{sale.id}'
                active_keys.add(key)
                _upsert_notification(
                    company_id, key=key, title=rule.name or 'Saldo por cobrar alto',
                    message=f'Venta #{sale.id} mantiene un saldo de {sale.balance}, superior al umbral {rule.threshold}.',
                    link='/backoffice/receivables', level=rule.level, user_id=rule.target_user_id,
                )
                produced += 1

        elif rule.rule_type == 'PAYABLE_DUE':
            days = max(int(rule.threshold or 0), 0)
            until = today + timedelta(days=days)
            bills = SupplierBill.query.filter(
                SupplierBill.company_id == company_id,
                SupplierBill.status != 'PAID', SupplierBill.due_date.isnot(None),
                SupplierBill.due_date >= today, SupplierBill.due_date <= until,
            ).order_by(SupplierBill.due_date.asc()).limit(150).all()
            for bill in bills:
                key = f'rule:{rule.id}:payable-due:{bill.id}'
                active_keys.add(key)
                _upsert_notification(
                    company_id, key=key, title=rule.name or 'Cuenta por pagar próxima',
                    message=f'{bill.document_number}: saldo {bill.balance}; vence {bill.due_date:%d/%m/%Y}.',
                    link='/backoffice/payables', level=rule.level, user_id=rule.target_user_id,
                )
                produced += 1

        elif rule.rule_type == 'PAYABLE_OVERDUE':
            bills = SupplierBill.query.filter(
                SupplierBill.company_id == company_id,
                SupplierBill.status != 'PAID', SupplierBill.due_date.isnot(None),
                SupplierBill.due_date < today,
            ).order_by(SupplierBill.due_date.asc()).limit(150).all()
            for bill in bills:
                key = f'rule:{rule.id}:payable-overdue:{bill.id}'
                active_keys.add(key)
                _upsert_notification(
                    company_id, key=key, title=rule.name or 'Cuenta por pagar vencida',
                    message=f'{bill.document_number}: saldo {bill.balance}; venció {bill.due_date:%d/%m/%Y}.',
                    link='/backoffice/payables', level=rule.level, user_id=rule.target_user_id,
                )
                produced += 1

        elif rule.rule_type == 'EXPENSE_AMOUNT_ABOVE':
            cutoff = today - timedelta(days=max(int(rule.lookback_days or 30), 0))
            expenses = Expense.query.filter(
                Expense.company_id == company_id, Expense.status == 'POSTED',
                Expense.expense_date >= cutoff, Expense.amount > max(int(rule.threshold or 0), 0),
            ).order_by(Expense.expense_date.desc()).limit(150).all()
            for expense in expenses:
                key = f'rule:{rule.id}:expense:{expense.id}'
                active_keys.add(key)
                _upsert_notification(
                    company_id, key=key, title=rule.name or 'Gasto elevado',
                    message=f'{expense.description}: importe {expense.amount}.',
                    link='/backoffice/expenses', level=rule.level, user_id=rule.target_user_id,
                )
                produced += 1

        elif rule.rule_type == 'SALE_AMOUNT_ABOVE':
            cutoff = utcnow() - timedelta(days=max(int(rule.lookback_days or 30), 0))
            sales = Sale.query.filter(
                Sale.company_id == company_id, Sale.status == 'COMPLETED',
                Sale.created_at >= cutoff, Sale.total > max(int(rule.threshold or 0), 0),
            ).order_by(Sale.created_at.desc()).limit(150).all()
            for sale in sales:
                key = f'rule:{rule.id}:sale:{sale.id}'
                active_keys.add(key)
                _upsert_notification(
                    company_id, key=key, title=rule.name or 'Venta de importe alto',
                    message=f'Venta #{sale.id}: total {sale.total}.',
                    link=f'/sales/{sale.id}', level=rule.level, user_id=rule.target_user_id,
                )
                produced += 1

        elif rule.rule_type == 'CUSTOM':
            produced += _evaluate_custom(rule, company_id, active_keys)

    stale = AppNotification.query.filter(
        AppNotification.company_id == company_id,
        AppNotification.read_at.is_(None),
        AppNotification.dedupe_key.like('rule:%'),
    ).all()
    now = utcnow()
    for notification in stale:
        if notification.dedupe_key not in active_keys:
            notification.read_at = now
    db.session.commit()
    return produced
