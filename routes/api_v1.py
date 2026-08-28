"""Versioned external API for retail integrations.

Authentication uses API keys created from Retail avanzado. API keys are tenant
scoped and carry comma separated scopes. The raw secret is never stored.
"""
from __future__ import annotations

import hashlib
from decimal import Decimal

from flask import Blueprint, g, jsonify, request
from sqlalchemy import func

from db import db
from models.retail import ApiKey, ProductBarcode, ProductVariant, WarehouseVariantStock
from models.products.products import Product
from models.warehouse.warehouse import Warehouse
from models.warehouse_stock.warehouse_stock import WarehouseStock
from models.client.client import Client
from models.sales.sales import Sale
from services.time_utils import utcnow

api_v1_bp = Blueprint('api_v1', __name__, url_prefix='/api/v1')


def _json_decimal(value):
    if value is None:
        return None
    return str(Decimal(value))


@api_v1_bp.before_request
def authenticate_api_key():
    auth = (request.headers.get('Authorization') or '').strip()
    if not auth.startswith('Bearer '):
        return jsonify({'error': 'API key requerida'}), 401
    raw = auth[7:].strip()
    if not raw.startswith('orb_') or len(raw) < 24:
        return jsonify({'error': 'API key inválida'}), 401
    key_hash = hashlib.sha256(raw.encode('utf-8')).hexdigest()
    api_key = ApiKey.query.filter_by(key_hash=key_hash, active=True).first()
    if not api_key or (api_key.expires_at and api_key.expires_at <= utcnow()):
        return jsonify({'error': 'API key inválida o expirada'}), 401
    api_key.last_used_at = utcnow()
    db.session.commit()
    g.api_key = api_key
    g.api_company_id = api_key.company_id


def _scope(scope):
    if not g.api_key.allows(scope):
        return jsonify({'error': 'Scope insuficiente', 'required': scope}), 403
    return None


def _pagination(query, default=50):
    limit = min(max(request.args.get('limit', default, type=int) or default, 1), 100)
    offset = max(request.args.get('offset', 0, type=int) or 0, 0)
    return query.limit(limit).offset(offset).all(), limit, offset


@api_v1_bp.get('/health')
def health():
    return jsonify({'ok': True, 'version': 'v1'})


@api_v1_bp.get('/products')
def products():
    denied = _scope('products:read')
    if denied: return denied
    q = Product.query.filter_by(company_id=g.api_company_id, status=True).filter(Product.archived_at.is_(None)).order_by(Product.id.asc())
    search = (request.args.get('q') or '').strip()
    if search:
        like = f'%{search}%'
        q = q.filter(db.or_(Product.name.ilike(like), Product.sku.ilike(like)))
    rows, limit, offset = _pagination(q)
    data = []
    for product in rows:
        data.append({
            'id': product.id, 'name': product.name, 'sku': product.sku,
            'brand': product.brand, 'type': product.product_type,
            'sale_mode': product.sale_mode, 'tracking': product.tracking,
            'price': _json_decimal(product.price), 'cost': _json_decimal(product.cost),
            'uom': product.base_uom.symbol if product.base_uom else None,
            'barcodes': [{'code': b.code, 'type': b.barcode_type, 'variant_id': b.variant_id} for b in product.barcodes],
            'variants': [{'id': v.id, 'sku': v.sku, 'name': v.name, 'attributes': v.attribute_summary, 'price': _json_decimal(v.display_price)} for v in product.variants if v.active],
        })
    return jsonify({'data': data, 'limit': limit, 'offset': offset})


@api_v1_bp.get('/inventory')
def inventory():
    denied = _scope('inventory:read')
    if denied: return denied
    warehouse_id = request.args.get('warehouse_id', type=int)
    q = WarehouseStock.query.filter_by(company_id=g.api_company_id)
    if warehouse_id:
        if not Warehouse.query.filter_by(id=warehouse_id, company_id=g.api_company_id, status=True).first():
            return jsonify({'error': 'Almacén inválido'}), 404
        q = q.filter_by(warehouse_id=warehouse_id)
    rows, limit, offset = _pagination(q.order_by(WarehouseStock.id.asc()))
    data = []
    for stock in rows:
        variants = WarehouseVariantStock.query.filter_by(company_id=g.api_company_id, warehouse_id=stock.warehouse_id, product_id=stock.product_id).all()
        data.append({
            'product_id': stock.product_id,
            'warehouse_id': stock.warehouse_id,
            'quantity': _json_decimal(stock.quantity),
            'variants': [{'variant_id': v.variant_id, 'quantity': _json_decimal(v.quantity)} for v in variants],
        })
    return jsonify({'data': data, 'limit': limit, 'offset': offset})


@api_v1_bp.get('/clients')
def clients():
    denied = _scope('clients:read')
    if denied: return denied
    q = Client.query.filter_by(company_id=g.api_company_id).filter(Client.archived_at.is_(None)).order_by(Client.id.asc())
    rows, limit, offset = _pagination(q)
    return jsonify({'data': [{
        'id': c.id, 'name': c.name, 'email': c.email, 'phone': c.phone,
        'credit_enabled': bool(c.credit_enabled), 'credit_limit': _json_decimal(c.credit_limit),
        'loyalty_points': _json_decimal(c.loyalty_points), 'price_list_id': c.price_list_id,
    } for c in rows], 'limit': limit, 'offset': offset})


@api_v1_bp.post('/clients')
def create_client():
    denied = _scope('clients:write')
    if denied: return denied
    payload = request.get_json(silent=True) or {}
    name = (payload.get('name') or '').strip()
    if len(name) < 2 or len(name) > 150:
        return jsonify({'error': 'Nombre inválido'}), 400
    client = Client(
        company_id=g.api_company_id, name=name,
        email=(payload.get('email') or '').strip()[:120] or None,
        phone=(payload.get('phone') or '').strip()[:50] or None,
    )
    db.session.add(client)
    db.session.commit()
    return jsonify({'id': client.id, 'name': client.name}), 201


@api_v1_bp.get('/sales')
def sales():
    denied = _scope('sales:read')
    if denied: return denied
    q = Sale.query.filter_by(company_id=g.api_company_id).order_by(Sale.created_at.desc(), Sale.id.desc())
    status = (request.args.get('status') or '').upper().strip()
    if status:
        q = q.filter_by(status=status)
    rows, limit, offset = _pagination(q)
    return jsonify({'data': [{
        'id': s.id, 'status': s.status, 'client_id': s.client_id,
        'warehouse_ids': sorted({i.warehouse_id for i in s.items if i.warehouse_id}),
        'subtotal': _json_decimal(s.subtotal), 'tax': _json_decimal(s.itbis),
        'discount': _json_decimal(s.discount_amount), 'total': _json_decimal(s.total),
        'paid': _json_decimal(s.amount_paid), 'balance': _json_decimal(s.balance),
        'created_at': s.created_at.isoformat() + 'Z' if s.created_at else None,
        'items': [{'product_id': i.product_id, 'variant_id': i.variant_id, 'quantity': _json_decimal(i.quantity), 'uom_id': i.uom_id, 'price': _json_decimal(i.price)} for i in s.items],
    } for s in rows], 'limit': limit, 'offset': offset})
