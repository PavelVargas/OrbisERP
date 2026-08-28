"""Real Flask render smoke tests for the commercial release.

These tests are intentionally PostgreSQL-only. They exercise actual request
routing, session validation, SQLAlchemy values and Jinja rendering — the layer
where previous Decimal/float and url_for regressions escaped static tests.
"""
import os
import secrets
from datetime import timedelta
from services.time_utils import utcnow
from decimal import Decimal

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv('TEST_DATABASE_URL'),
    reason='Requiere PostgreSQL de pruebas explícito para render HTTP real',
)


def _seed_release_fixture():
    from app import app
    from db import db
    from models.client.client import Client
    from models.company.company import Company
    from models.products.products import Product, ProductType
    from models.sales.sales import Sale
    from models.sales.sale_item import SaleItem
    from models.user.user import User
    from models.warehouse.warehouse import Warehouse
    from models.operations import UserSession
    from security import hash_session_token

    suffix = secrets.token_hex(6)
    with app.app_context():
        company = Company(
            name=f'HTTP QA {suffix}',
            rnc=None,
            plan_name='ULTRA',
            plan_status='ACTIVE',
            status=True,
            expiration_date=utcnow() + timedelta(days=30),
            onboarding_completed=True,
        )
        db.session.add(company)
        db.session.flush()

        warehouse = Warehouse(
            name='Almacén QA', location='Pruebas', status=True, is_main=True,
            company_id=company.id,
        )
        db.session.add(warehouse)
        db.session.flush()

        user = User(
            name='Admin QA', email=f'qa-{suffix}@example.invalid', password='pending-hash',
            cedula=f'QA-{suffix}', role='admin', company_id=company.id,
            warehouse_id=warehouse.id, default_currency='DOP',
            email_verified_at=utcnow(),
        )
        user.set_password('ReleaseQA-2026-Strong')
        db.session.add(user)
        db.session.flush()

        client = Client(name='Cliente QA', email=f'client-{suffix}@example.invalid', company_id=company.id)
        db.session.add(client)
        product = Product(
            name='Servicio QA', sku=f'SVC-{suffix}', price=Decimal('125.50'), cost=Decimal('50.25'),
            min_stock=0, company_id=company.id, product_type=ProductType.SERVICE, status=True,
        )
        db.session.add(product)
        db.session.flush()

        sale = Sale(
            customer_name=client.name, subtotal=Decimal('100.00'), itbis=Decimal('18.00'),
            total=Decimal('118.00'), amount_paid=Decimal('18.00'), balance=Decimal('100.00'),
            user_id=user.id, client_id=client.id, company_id=company.id, status='COMPLETED',
            payment_method='CASH',
        )
        db.session.add(sale)
        db.session.flush()
        db.session.add(SaleItem(
            sale_id=sale.id, product_id=product.id, warehouse_id=warehouse.id, quantity=1,
            price=Decimal('118.00'), tax_name='ITBIS 18%', tax_rate=Decimal('18.00'), tax_included=True,
        ))

        raw_token = secrets.token_urlsafe(32)
        db.session.add(UserSession(
            session_hash=hash_session_token(raw_token), user_id=user.id, company_id=company.id,
            ip_address='127.0.0.1', user_agent='pytest', created_at=utcnow(),
            last_seen_at=utcnow(),
        ))
        db.session.commit()
        return {
            'company_id': company.id,
            'warehouse_id': warehouse.id,
            'user_id': user.id,
            'session_version': user.session_version,
            'client_id': client.id,
            'token': raw_token,
        }


def _authenticated_client(seed):
    from app import app

    client = app.test_client()
    with client.session_transaction() as session:
        session['user_id'] = seed['user_id']
        session['user_name'] = 'Admin QA'
        session['user_role'] = 'admin'
        session['company_id'] = seed['company_id']
        session['warehouse_id'] = seed['warehouse_id']
        session['session_version'] = seed['session_version']
        session['selected_currency'] = 'DOP'
        session['currency_symbol'] = 'RD$'
        session['server_session_token'] = seed['token']
        session.permanent = True
    return client


def test_critical_authenticated_pages_render_against_postgresql():
    seed = _seed_release_fixture()
    client = _authenticated_client(seed)

    pages = [
        '/dashboard',
        '/list_product',
        f'/clients/{seed["client_id"]}',
        '/crm',
        '/sales/',
        '/warehouses/',
        '/cash/register',
        '/workspace/documents',
        '/workspace/notification-rules',
        '/governance/audit',
        '/governance/integrity',
        '/governance/system',
        '/retail/',
        '/retail/warranties',
        '/retail/quality',
        '/reports/retail-performance',
        '/perfil',
    ]
    failures = []
    for path in pages:
        response = client.get(path, follow_redirects=False)
        if response.status_code != 200:
            failures.append((path, response.status_code, response.get_data(as_text=True)[:300]))
    assert not failures, failures


def test_product_archive_round_trip_renders_without_money_type_error():
    from app import app
    from models.products.products import Product

    seed = _seed_release_fixture()
    client = _authenticated_client(seed)
    with app.app_context():
        product = Product.query.filter_by(company_id=seed['company_id']).first()
        product_id = product.id

    # Fetching the form page first gives the security layer a CSRF token.
    response = client.get('/list_product')
    assert response.status_code == 200
    with client.session_transaction() as session:
        csrf = session['_csrf_token']

    response = client.post(
        f'/delete_product/{product_id}',
        data={'_csrf_token': csrf, '_idempotency_key': secrets.token_urlsafe(24)},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b'500 Internal Server Error' not in response.data

    response = client.get('/list_product?scope=archived')
    assert response.status_code == 200
