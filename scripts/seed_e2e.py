#!/usr/bin/env python3
"""Idempotent seed for browser smoke tests. Never run against production."""
import os
import sys
from pathlib import Path
from decimal import Decimal
from datetime import timedelta

# Permite ejecutar este archivo directamente desde scripts/
# sin perder acceso a app.py y los paquetes de la raiz.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if os.getenv('APP_ENV') not in {'testing', 'development'}:
    raise SystemExit('seed_e2e.py solo puede ejecutarse con APP_ENV=testing/development')

from app import app
from db import db
from models.company.company import Company
from models.user.user import User
from models.warehouse.warehouse import Warehouse
from models.client.client import Client
from models.products.products import Product, ProductType
from services.time_utils import utcnow

EMAIL = 'e2e.admin@orbiserp.test'
PASSWORD = 'E2E-Release-2026-Strong'

with app.app_context():
    user = User.query.filter_by(email=EMAIL).first()
    if user:
        company = db.session.get(Company, user.company_id)
    else:
        company = Company(
            name='OrbisERP E2E', status=True, plan_name='ULTRA', plan_status='ACTIVE',
            expiration_date=utcnow() + timedelta(days=30), onboarding_completed=True,
        )
        db.session.add(company)
        db.session.flush()
        warehouse = Warehouse(name='Almacén E2E', location='QA', status=True, is_main=True, company_id=company.id)
        db.session.add(warehouse)
        db.session.flush()
        user = User(
            name='Admin E2E', email=EMAIL, password='pending-hash', cedula='E2E-0001',
            role='admin', company_id=company.id, warehouse_id=warehouse.id,
            default_currency='DOP', email_verified_at=utcnow(),
        )
        user.set_password(PASSWORD)
        db.session.add(user)
        db.session.add(Client(name='Cliente E2E', email='client.e2e@orbiserp.test', company_id=company.id))
        db.session.add(Product(
            name='Servicio E2E', sku='E2E-SERVICE', price=Decimal('100.00'), cost=Decimal('25.00'),
            min_stock=0, company_id=company.id, product_type=ProductType.SERVICE, status=True,
        ))
    if company:
        company.status = True
        company.expiration_date = utcnow() + timedelta(days=30)
    user.is_active = True
    user.email_verified_at = user.email_verified_at or utcnow()
    user.set_password(PASSWORD)
    db.session.commit()
print(EMAIL)
