import csv
import hashlib
import hmac
import io
import json
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from flask import Blueprint, Response, abort, current_app, flash, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from db import db
from models.category.category import Category
from models.client.client import Client
from models.company.company import Company
from models.operations import BillingInvoice, SubscriptionEvent
from models.products.products import Product, ProductType
from models.supplier.supplier import Supplier
from models.user.user import User
from models.warehouse.warehouse import Warehouse
from models.warehouse_stock.warehouse_stock import WarehouseStock


operations_bp = Blueprint('operations_bp', __name__, url_prefix='/operations')


def _company():
    return Company.query.filter_by(id=session.get('company_id')).first_or_404()


def _parse_datetime(value):
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace('Z', '+00:00')).replace(tzinfo=None)


@operations_bp.get('/health/live')
def health_live():
    return jsonify(status='ok', service='orbiserp')


@operations_bp.get('/health/ready')
def health_ready():
    try:
        db.session.execute(text('SELECT 1'))
        return jsonify(status='ready', database='ok')
    except Exception:
        current_app.logger.exception('Readiness check failed')
        return jsonify(status='unavailable', database='error'), 503


@operations_bp.route('/setup', methods=['GET', 'POST'])
def onboarding():
    company = _company()
    user = db.session.get(User, session.get('user_id'))
    if request.method == 'POST':
        company.name = (request.form.get('name') or company.name).strip()[:150]
        company.rnc = (request.form.get('rnc') or '').strip()[:20] or None
        company.email = (request.form.get('email') or '').strip()[:120] or None
        company.phone = (request.form.get('phone') or '').strip()[:20] or None
        company.address = (request.form.get('address') or '').strip() or None
        warehouse_name = (request.form.get('warehouse_name') or '').strip()
        if warehouse_name and not Warehouse.query.filter_by(company_id=company.id).first():
            db.session.add(Warehouse(name=warehouse_name[:150], location=company.address, is_main=True, company_id=company.id))
        company.onboarding_completed = True
        db.session.commit()
        flash('Configuración inicial completada. Tu empresa está lista para operar.', 'success')
        return redirect(url_for('dashboard_bp.dashboard'))
    return render_template('operations/setup.html', company=company, user=user)


@operations_bp.get('/billing')
def billing():
    company = _company()
    user = db.session.get(User, session.get('user_id'))
    invoices = BillingInvoice.query.filter_by(company_id=company.id).order_by(BillingInvoice.created_at.desc()).limit(24).all()
    return render_template('operations/billing.html', company=company, invoices=invoices, user=user)


@operations_bp.post('/billing/webhook')
def billing_webhook():
    secret = current_app.config.get('BILLING_WEBHOOK_SECRET', '')
    if not secret:
        return jsonify(error='Webhook no configurado'), 503
    raw = request.get_data(cache=True)
    received = request.headers.get('X-Orbis-Signature', '')
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(received, expected):
        abort(401)
    payload = request.get_json(silent=True) or {}
    event_id = str(payload.get('id') or '')[:150]
    event_type = str(payload.get('type') or '')[:80]
    company_id = payload.get('company_id')
    if not event_id or not event_type or not isinstance(company_id, int):
        return jsonify(error='Evento incompleto'), 400
    if SubscriptionEvent.query.filter_by(event_id=event_id).first():
        return jsonify(status='duplicate'), 200
    event = SubscriptionEvent(event_id=event_id, event_type=event_type, company_id=company_id,
                              provider=str(payload.get('provider') or 'generic')[:40],
                              payload_hash=hashlib.sha256(raw).hexdigest())
    db.session.add(event)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return jsonify(status='duplicate'), 200
    company = db.session.get(Company, company_id)
    if not company:
        event.error = 'Empresa no encontrada'
        db.session.commit()
        return jsonify(error=event.error), 404
    data = payload.get('data') or {}
    try:
        if event_type in {'payment.succeeded', 'subscription.activated', 'subscription.renewed'}:
            plan = str(data.get('plan') or company.plan_name).upper()
            if plan not in {'BASIC', 'PRO', 'ULTRA'}:
                raise ValueError('Plan inválido')
            company.plan_name = plan
            company.plan_status = 'ACTIVE'
            company.status = True
            company.is_readonly = False
            company.billing_provider = event.provider
            company.billing_customer_id = str(data.get('customer_id') or '')[:120] or company.billing_customer_id
            company.billing_subscription_id = str(data.get('subscription_id') or '')[:120] or company.billing_subscription_id
            company.expiration_date = _parse_datetime(data.get('period_end')) or datetime.utcnow() + timedelta(days=30)
            company.grace_period_until = None
            external_id = str(data.get('invoice_id') or event_id)[:120]
            invoice = BillingInvoice.query.filter_by(external_id=external_id).first()
            if not invoice:
                invoice = BillingInvoice(company_id=company.id, external_id=external_id, provider=event.provider,
                                         status='PAID', plan_name=plan, amount=Decimal(str(data.get('amount') or 0)),
                                         currency=str(data.get('currency') or 'DOP')[:3].upper(),
                                         period_start=_parse_datetime(data.get('period_start')),
                                         period_end=company.expiration_date, paid_at=datetime.utcnow())
                db.session.add(invoice)
        elif event_type == 'payment.failed':
            company.plan_status = 'PAST_DUE'
            company.grace_period_until = datetime.utcnow() + timedelta(days=3)
        elif event_type == 'subscription.cancelled':
            company.plan_status = 'CANCELLED'
            company.cancel_at_period_end = True
        else:
            raise ValueError('Tipo de evento no soportado')
        event.processed = True
        db.session.commit()
    except (ValueError, InvalidOperation) as exc:
        db.session.rollback()
        return jsonify(error=str(exc)), 400
    return jsonify(status='processed')


@operations_bp.route('/data', methods=['GET', 'POST'])
def data_center():
    company = _company()
    user = db.session.get(User, session.get('user_id'))
    report = []
    if request.method == 'POST':
        kind = request.form.get('kind')
        upload = request.files.get('file')
        if kind not in {'products', 'clients', 'suppliers'} or not upload or not upload.filename.lower().endswith('.csv'):
            flash('Selecciona un tipo y un archivo CSV válido.', 'danger')
            return redirect(request.url)
        try:
            content = upload.stream.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            flash('El CSV debe estar codificado en UTF-8.', 'danger')
            return redirect(request.url)
        rows = list(csv.DictReader(io.StringIO(content)))
        if len(rows) > 5000:
            flash('El archivo supera el máximo de 5,000 filas por importación.', 'danger')
            return redirect(request.url)
        for number, row in enumerate(rows, 2):
            try:
                if kind == 'products':
                    _import_product(company.id, row)
                elif kind == 'clients':
                    _import_client(company.id, row)
                else:
                    _import_supplier(company.id, row)
            except (ValueError, InvalidOperation) as exc:
                report.append(f'Fila {number}: {exc}')
        if report:
            db.session.rollback()
            flash(f'Importación detenida: corrige {len(report)} filas.', 'warning')
        else:
            db.session.commit()
            flash(f'{len(rows)} registros importados correctamente.', 'success')
        return render_template('operations/data_center.html', company=company, user=user, report=report)
    return render_template('operations/data_center.html', company=company, user=user, report=report)


def _import_product(company_id, row):
    name, sku = (row.get('name') or '').strip(), (row.get('sku') or '').strip()
    if not name or not sku:
        raise ValueError('name y sku son obligatorios')
    price, cost = Decimal(row.get('price') or '0'), Decimal(row.get('cost') or '0')
    if price < 0 or cost < 0:
        raise ValueError('precio y costo no pueden ser negativos')
    if Product.query.filter_by(company_id=company_id, sku=sku).first():
        raise ValueError(f'SKU duplicado: {sku}')
    category = None
    category_name = (row.get('category') or '').strip()
    if category_name:
        category = Category.query.filter(db.func.lower(Category.name) == category_name.lower(), Category.company_id == company_id).first()
        if not category:
            category = Category(name=category_name[:100], company_id=company_id, status=True)
            db.session.add(category)
            db.session.flush()
    type_name = (row.get('type') or 'STOCKED').upper()
    if type_name not in ProductType.__members__:
        raise ValueError(f'tipo inválido: {type_name}')
    product = Product(name=name[:150], sku=sku[:50], description=(row.get('description') or '').strip() or None,
                      price=price, cost=cost, category_id=category.id if category else None,
                      product_type=ProductType[type_name], company_id=company_id, status=True)
    db.session.add(product)
    db.session.flush()
    stock_value = Decimal(row.get('stock') or '0')
    if stock_value < 0 or stock_value != stock_value.to_integral_value():
        raise ValueError('stock debe ser un entero no negativo')
    stock = int(stock_value)
    if stock and product.product_type != ProductType.SERVICE:
        warehouse = Warehouse.query.filter_by(company_id=company_id, is_main=True, status=True).first()
        if not warehouse:
            raise ValueError('crea un almacén principal antes de importar inventario')
        db.session.add(WarehouseStock(product_id=product.id, warehouse_id=warehouse.id,
                                      quantity=stock, company_id=company_id))


def _import_client(company_id, row):
    name = (row.get('name') or '').strip()
    if not name:
        raise ValueError('name es obligatorio')
    db.session.add(Client(name=name[:150], email=(row.get('email') or '').strip()[:120] or None,
                          phone=(row.get('phone') or '').strip()[:20] or None,
                          status=(row.get('status') or 'Lead')[:50], company_id=company_id))


def _import_supplier(company_id, row):
    name = (row.get('name') or '').strip()
    if not name:
        raise ValueError('name es obligatorio')
    db.session.add(Supplier(name=name[:150], email=(row.get('email') or '').strip()[:120] or None,
                            phone=(row.get('phone') or '').strip()[:50] or None, company_id=company_id))


@operations_bp.get('/data/export/<kind>.csv')
def export_data(kind):
    company_id = session.get('company_id')
    output = io.StringIO()
    writer = csv.writer(output)
    if kind == 'products':
        writer.writerow(['name', 'sku', 'description', 'price', 'cost', 'type', 'category', 'stock'])
        for p in Product.query.filter_by(company_id=company_id).order_by(Product.name).all():
            writer.writerow([p.name, p.sku, p.description or '', p.price, p.cost, p.product_type.name, p.category.name if p.category else '', p.total_stock])
    elif kind == 'clients':
        writer.writerow(['name', 'email', 'phone', 'status'])
        for c in Client.query.filter_by(company_id=company_id).order_by(Client.name).all():
            writer.writerow([c.name, c.email or '', c.phone or '', c.status])
    elif kind == 'suppliers':
        writer.writerow(['name', 'email', 'phone'])
        for s in Supplier.query.filter_by(company_id=company_id).order_by(Supplier.name).all():
            writer.writerow([s.name, s.email or '', s.phone or ''])
    else:
        abort(404)
    return Response('\ufeff' + output.getvalue(), mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename=orbiserp_{kind}.csv'})


@operations_bp.get('/data/template/<kind>.csv')
def download_import_template(kind):
    """Plantillas mínimas para evitar encabezados inválidos al importar."""
    headers = {
        'products': ['name', 'sku', 'description', 'price', 'cost', 'type', 'category', 'stock'],
        'clients': ['name', 'email', 'phone', 'status'],
        'suppliers': ['name', 'email', 'phone'],
    }
    if kind not in headers:
        abort(404)
    output = io.StringIO()
    csv.writer(output).writerow(headers[kind])
    return Response('\ufeff' + output.getvalue(), mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename=plantilla_{kind}.csv'})
