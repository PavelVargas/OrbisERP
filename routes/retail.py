from __future__ import annotations

from services.numeric import NumericValueError, bounded_decimal, finite_decimal, finite_int
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_CEILING
from itertools import product as cartesian_product
import hashlib
import re
import secrets

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, g, abort, current_app
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from db import db
from services.time_utils import utcnow
from services.quantity import positive_quantity, non_negative_quantity, product_quantity, as_decimal
from services.validation import BusinessRuleError, positive_money, tenant_id
from services.retail import get_retail_settings, resolve_sale_price, release_serials_for_item, uom_factor_to_base
from services.sale_engine import ensure_item_available, finalize_sale_inventory_and_loyalty
from services.webhooks import validate_webhook_url, emit_event
from models.user.user import User
from models.company.company import Company
from models.products.products import Product, ProductType
from models.category.category import Category
from models.client.client import Client
from models.supplier.supplier import Supplier
from models.warehouse.warehouse import Warehouse
from models.warehouse_stock.warehouse_stock import WarehouseStock
from models.stock_movement.stock_movement import StockMovement
from models.sales.sales import Sale
from models.sales.sale_item import SaleItem
from models.purchase.purchase_order import PurchaseOrder
from models.purchase.purchase_order_item import PurchaseOrderItem
from models.retail import (
    CompanyRetailSettings, Branch, PosTerminal, UnitOfMeasure, ProductUomConversion,
    ProductAttribute, ProductAttributeValue, ProductVariant, ProductVariantValue,
    ProductBarcode, WarehouseVariantStock, PriceList, PriceListRule, ProductSupplier,
    ProductBundleItem, InventoryLot, InventorySerial, WarrantyClaim, GiftCard, SalePayment,
    LoyaltyTransaction, Layaway, LayawayPayment, StockReservation, ApprovalRule,
    ApprovalRequest, ApiKey, OutboundWebhook, InventorySerialEvent, InventoryConditionStock,
    SaleReturnItemLotAllocation, SaleReturnItemSerial,
)

retail_bp = Blueprint('retail_bp', __name__, url_prefix='/retail')


def _ctx():
    company_id = session.get('company_id')
    user_id = session.get('user_id')
    if not company_id or not user_id:
        return None, None
    return int(company_id), db.session.get(User, int(user_id))


def _slug(value):
    text = re.sub(r'[^A-Z0-9]+', '-', (value or '').upper()).strip('-')
    return text[:24] or 'VAR'


def _redirect_product(product_id):
    return redirect(url_for('products_bp.view_product', id=product_id, tab=request.form.get('return_tab', 'retail')))


def _optional_tenant_id(raw, field):
    if raw is None or not str(raw).strip():
        return None
    return tenant_id(raw, field)


def _replenishment_rows(company_id, *, limit=100):
    """Calculate low-stock suggestions with bounded, tenant-scoped queries."""
    products = (
        Product.query.options(
            selectinload(Product.supplier_links).selectinload(ProductSupplier.supplier)
        )
        .filter_by(company_id=company_id, status=True)
        .filter(Product.archived_at.is_(None))
        .all()
    )
    stock_totals = {}
    product_ids = [product.id for product in products]
    if product_ids:
        stock_totals = {
            product_id: as_decimal(total)
            for product_id, total in db.session.query(
                WarehouseStock.product_id,
                func.coalesce(func.sum(WarehouseStock.quantity), 0),
            )
            .filter(
                WarehouseStock.company_id == company_id,
                WarehouseStock.product_id.in_(product_ids),
            )
            .group_by(WarehouseStock.product_id)
            .all()
        }

    rows = []
    for product in products:
        if product.product_type == ProductType.SERVICE:
            continue
        current = stock_totals.get(product.id, finite_decimal('0'))
        minimum = as_decimal(product.min_stock or 0)
        target = (
            as_decimal(product.max_stock)
            if product.max_stock is not None
            else max(minimum * finite_decimal('2'), minimum + finite_decimal('1'))
        )
        if current > minimum or target <= current:
            continue

        links = [
            link for link in product.supplier_links
            if link.supplier and getattr(link.supplier, 'archived_at', None) is None
        ]
        preferred = next((link for link in links if link.preferred), None)
        if not preferred and links:
            preferred = min(
                links,
                key=lambda link: (as_decimal(link.unit_cost), int(link.lead_time_days or 0)),
            )
        rows.append({
            'product': product,
            'current': current,
            'suggested': max(target - current, finite_decimal('0')),
            'supplier': preferred.supplier if preferred else None,
            'supplier_link': preferred,
        })

    rows.sort(
        key=lambda row: (
            row['current'] - as_decimal(row['product'].min_stock or 0),
            row['product'].name,
        )
    )
    return rows[:limit]


def _retail_settings(company_id):
    settings = get_retail_settings(company_id, create=True)
    # Warranties are a core retail baseline in this release.
    if not settings.enable_warranties:
        settings.enable_warranties = True
    db.session.commit()
    return settings


@retail_bp.get('/')
def overview():
    company_id, user = _ctx()
    if not company_id:
        return redirect(url_for('login_bp.login'))
    settings = _retail_settings(company_id)
    replenishment = _replenishment_rows(company_id, limit=8)
    metrics = {
        'branches': Branch.query.filter_by(company_id=company_id, status=True).count(),
        'terminals': PosTerminal.query.filter_by(company_id=company_id, status=True).count(),
        'price_lists': PriceList.query.filter_by(company_id=company_id, active=True).count(),
        'products': Product.query.filter_by(company_id=company_id, status=True).filter(Product.archived_at.is_(None)).count(),
        'warranties': WarrantyClaim.query.filter(
            WarrantyClaim.company_id == company_id,
            WarrantyClaim.status.in_(['OPEN', 'IN_REVIEW', 'APPROVED']),
        ).count(),
        'layaways': Layaway.query.filter_by(company_id=company_id, status='OPEN').count(),
        'approvals': ApprovalRequest.query.filter_by(company_id=company_id, status='PENDING').count(),
        'replenishment': len(replenishment),
    }
    return render_template('retail/overview.html', user=user, settings=settings, metrics=metrics, replenishment=replenishment)


@retail_bp.get('/configuration')
def configuration():
    company_id, user = _ctx()
    if not company_id:
        return redirect(url_for('login_bp.login'))
    return render_template('retail/configuration.html', user=user, settings=_retail_settings(company_id))


@retail_bp.get('/locations')
def locations():
    company_id, user = _ctx()
    if not company_id:
        return redirect(url_for('login_bp.login'))
    branches = Branch.query.filter_by(company_id=company_id).order_by(Branch.is_main.desc(), Branch.name.asc()).all()
    terminals = PosTerminal.query.filter_by(company_id=company_id).order_by(PosTerminal.name.asc()).all()
    warehouses = Warehouse.query.filter_by(company_id=company_id, status=True).order_by(Warehouse.is_main.desc(), Warehouse.name.asc()).all()
    return render_template('retail/locations.html', user=user, branches=branches, terminals=terminals, warehouses=warehouses)


@retail_bp.get('/catalog-setup')
def catalog_setup():
    company_id, user = _ctx()
    if not company_id:
        return redirect(url_for('login_bp.login'))
    uoms = UnitOfMeasure.query.filter_by(company_id=company_id, active=True).order_by(UnitOfMeasure.category.asc(), UnitOfMeasure.name.asc()).all()
    attributes = ProductAttribute.query.filter_by(company_id=company_id, active=True).order_by(ProductAttribute.sequence.asc(), ProductAttribute.name.asc()).all()
    active_products = Product.query.filter_by(company_id=company_id, status=True).filter(Product.archived_at.is_(None))
    product_count = active_products.count()
    products_missing_sale_uom = active_products.filter(Product.sale_uom_id.is_(None)).count()
    products_missing_base_uom = active_products.filter(Product.base_uom_id.is_(None)).count()
    return render_template(
        'retail/catalog_setup.html',
        user=user,
        uoms=uoms,
        attributes=attributes,
        product_count=product_count,
        products_missing_sale_uom=products_missing_sale_uom,
        products_missing_base_uom=products_missing_base_uom,
    )


@retail_bp.get('/pricing')
def pricing():
    company_id, user = _ctx()
    if not company_id:
        return redirect(url_for('login_bp.login'))
    price_lists = PriceList.query.filter_by(company_id=company_id).order_by(PriceList.is_default.desc(), PriceList.name.asc()).all()
    products_active = Product.query.filter_by(company_id=company_id, status=True).filter(Product.archived_at.is_(None)).order_by(Product.name.asc()).all()
    categories = Category.query.filter_by(company_id=company_id, status=True).order_by(Category.name.asc()).all()
    return render_template('retail/pricing.html', user=user, price_lists=price_lists, products_active=products_active, categories=categories)


@retail_bp.get('/customer-programs')
def customer_programs():
    company_id, user = _ctx()
    if not company_id:
        return redirect(url_for('login_bp.login'))

    can_loyalty = bool(user and user.has_permission('clients.loyalty'))
    can_giftcards = bool(user and user.has_permission('sales.giftcards'))
    can_layaways = bool(user and user.has_permission('sales.layaway'))

    settings = _retail_settings(company_id) if can_loyalty else None
    loyalty_client_count = (
        Client.query.filter_by(company_id=company_id, archived_at=None).count()
        if can_loyalty else 0
    )
    clients = (
        Client.query.filter_by(company_id=company_id, archived_at=None)
        .order_by(Client.name.asc()).all()
        if can_giftcards else []
    )
    gift_cards = (
        GiftCard.query.filter_by(company_id=company_id)
        .order_by(GiftCard.created_at.desc()).limit(80).all()
        if can_giftcards else []
    )
    layaways = (
        Layaway.query.filter_by(company_id=company_id)
        .order_by(Layaway.created_at.desc()).limit(80).all()
        if can_layaways else []
    )
    initial_panel = (
        'loyalty' if can_loyalty else 'giftcards' if can_giftcards else 'layaways'
    )
    return render_template(
        'retail/customer_programs.html',
        user=user,
        settings=settings,
        clients=clients,
        loyalty_client_count=loyalty_client_count,
        gift_cards=gift_cards,
        layaways=layaways,
        can_loyalty=can_loyalty,
        can_giftcards=can_giftcards,
        can_layaways=can_layaways,
        initial_panel=initial_panel,
    )


@retail_bp.get('/operations-center')
def operations_center():
    company_id, user = _ctx()
    if not company_id:
        return redirect(url_for('login_bp.login'))

    can_replenishment = bool(user and user.has_permission('inventory.replenishment'))
    can_approvals = bool(user and user.has_permission('approvals.manage'))
    can_warranties = bool(user and user.has_permission('sales.warranties'))
    can_quality = bool(user and user.has_permission('stock.adjust'))

    replenishment = _replenishment_rows(company_id) if can_replenishment else []
    suppliers = (
        Supplier.query.filter_by(company_id=company_id, archived_at=None)
        .order_by(Supplier.name.asc()).all()
        if can_replenishment else []
    )
    approval_rules = (
        ApprovalRule.query.filter_by(company_id=company_id)
        .order_by(ApprovalRule.operation_type.asc()).all()
        if can_approvals else []
    )
    approvals = (
        ApprovalRequest.query.filter_by(company_id=company_id, status='PENDING')
        .order_by(ApprovalRequest.created_at.asc()).all()
        if can_approvals else []
    )
    warranty_open = (
        WarrantyClaim.query.filter(
            WarrantyClaim.company_id == company_id,
            WarrantyClaim.status.in_(['OPEN', 'IN_REVIEW', 'APPROVED']),
        ).count()
        if can_warranties else 0
    )
    quality_held = (
        db.session.query(func.coalesce(func.sum(InventoryConditionStock.quantity), 0))
        .filter(InventoryConditionStock.company_id == company_id).scalar()
        if can_quality else finite_decimal('0')
    )
    initial_panel = 'replenishment' if can_replenishment else 'approvals'
    return render_template(
        'retail/operations_center.html',
        user=user,
        replenishment=replenishment,
        suppliers=suppliers,
        approval_rules=approval_rules,
        approvals=approvals,
        warranty_open=warranty_open,
        quality_held=quality_held,
        can_replenishment=can_replenishment,
        can_approvals=can_approvals,
        can_warranties=can_warranties,
        can_quality=can_quality,
        initial_panel=initial_panel,
    )


@retail_bp.get('/integrations')
def integrations():
    company_id, user = _ctx()
    if not company_id:
        return redirect(url_for('login_bp.login'))
    api_keys = ApiKey.query.filter_by(company_id=company_id).order_by(ApiKey.created_at.desc()).all()
    webhooks = OutboundWebhook.query.filter_by(company_id=company_id).order_by(OutboundWebhook.created_at.desc()).all()
    return render_template(
        'retail/integrations.html', user=user, api_keys=api_keys, webhooks=webhooks,
        generated_api_key=session.pop('generated_api_key', None),
    )


@retail_bp.post('/settings')
def settings_update():
    company_id, _ = _ctx()
    settings = get_retail_settings(company_id, create=True)
    profiles = {'GENERAL','FASHION','TECH','HARDWARE','GROCERY','DISTRIBUTION','COSMETICS','FURNITURE','OTHER'}
    profile = (request.form.get('industry_profile') or 'GENERAL').upper()
    settings.industry_profile = profile if profile in profiles else 'GENERAL'
    toggles = [
        'enable_variants','enable_uom','enable_price_lists','enable_lots','enable_serials','enable_expirations',
        'enable_bundles','enable_credit','enable_loyalty','enable_gift_cards','enable_terminals',
        'enable_layaway','enable_replenishment',
    ]
    for name in toggles:
        setattr(settings, name, request.form.get(name) == '1')
    # Garantías forman parte del núcleo comercial: todos los productos tienen
    # un plazo y la empresa no puede desactivar accidentalmente la postventa.
    settings.enable_warranties = True
    method = (request.form.get('costing_method') or 'AVERAGE').upper()
    settings.costing_method = method if method in {'AVERAGE','FIFO','LAST'} else 'AVERAGE'
    try:
        receipt_width = int(request.form.get('default_receipt_width') or 80)
    except (TypeError, ValueError):
        receipt_width = 80
    if not 40 <= receipt_width <= 112:
        flash('El ancho del ticket debe estar entre 40 y 112 mm.', 'danger')
        return redirect(url_for('retail_bp.configuration'))
    printer_mode = (request.form.get('receipt_printer_mode') or 'BROWSER').upper()
    if printer_mode not in {'BROWSER', 'WEBUSB', 'ELECTRON'}:
        printer_mode = 'BROWSER'
    settings.default_receipt_width = receipt_width
    settings.receipt_printer_mode = printer_mode
    settings.receipt_printer_name = (request.form.get('receipt_printer_name') or '').strip()[:160] or None
    settings.receipt_auto_print = request.form.get('receipt_auto_print') == '1'
    try:
        settings.loyalty_points_per_currency = bounded_decimal(
            request.form.get('loyalty_points_per_currency') or 0,
            field_name='Puntos por moneda', places=4, minimum='0', maximum='99999999.9999',
        )
        settings.loyalty_currency_per_point = bounded_decimal(
            request.form.get('loyalty_currency_per_point') or 0,
            field_name='Valor por punto', places=4, minimum='0', maximum='99999999.9999',
        )
    except BusinessRuleError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('retail_bp.configuration'))
    db.session.commit()
    flash('Configuración retail actualizada.', 'success')
    return redirect(url_for('retail_bp.configuration'))


@retail_bp.post('/branches')
def branch_create():
    company_id, _ = _ctx()
    name = (request.form.get('name') or '').strip()
    code = _slug(request.form.get('code') or name)[:30]
    if not name:
        flash('Indica el nombre de la sucursal.', 'danger')
        return redirect(url_for('retail_bp.locations'))
    if request.form.get('is_main') == '1':
        Branch.query.filter_by(company_id=company_id).update({'is_main': False})
    db.session.add(Branch(company_id=company_id, code=code, name=name,
                          address=(request.form.get('address') or '').strip() or None,
                          phone=(request.form.get('phone') or '').strip() or None,
                          is_main=request.form.get('is_main') == '1'))
    try:
        db.session.commit()
        flash('Sucursal creada.', 'success')
    except IntegrityError:
        db.session.rollback()
        flash('Ya existe una sucursal con ese código.', 'danger')
    return redirect(url_for('retail_bp.locations'))


@retail_bp.post('/terminals')
def terminal_create():
    company_id, _ = _ctx()
    try:
        warehouse_id = tenant_id(request.form.get('warehouse_id'), 'Almacén')
    except BusinessRuleError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('retail_bp.locations'))
    warehouse = Warehouse.query.filter_by(id=warehouse_id, company_id=company_id, status=True).first_or_404()
    branch_id = request.form.get('branch_id', type=int)
    if branch_id and not Branch.query.filter_by(id=branch_id, company_id=company_id, status=True).first():
        branch_id = None
    name = (request.form.get('name') or '').strip()
    code = _slug(request.form.get('code') or name)[:30]
    if not name:
        flash('Indica el nombre de la terminal.', 'danger')
        return redirect(url_for('retail_bp.locations'))
    db.session.add(PosTerminal(company_id=company_id, branch_id=branch_id, warehouse_id=warehouse.id,
                               code=code, name=name, receipt_width=max(40, min(112, request.form.get('receipt_width', type=int) or 80))))
    try:
        db.session.commit(); flash('Terminal POS creada.', 'success')
    except IntegrityError:
        db.session.rollback(); flash('Ya existe una terminal con ese código.', 'danger')
    return redirect(url_for('retail_bp.locations'))


@retail_bp.post('/catalog-setup/apply-uom-all')
def apply_uom_to_all_products():
    """Set one sale UOM across the active catalog without inventing conversions.

    Products without a base unit receive the selected unit as both base and sale
    UOM. Products with a base unit are updated only when the measurement category
    is compatible; existing product conversions are preserved and, when present,
    explicitly enabled for sale.
    """
    company_id, _ = _ctx()
    if not company_id:
        return redirect(url_for('login_bp.login'))

    uom_id = request.form.get('uom_id', type=int)
    selected = UnitOfMeasure.query.filter_by(id=uom_id, company_id=company_id, active=True).first()
    if not selected:
        flash('Selecciona una unidad de medida válida.', 'danger')
        return redirect(url_for('retail_bp.catalog_setup'))

    products = (
        Product.query.filter_by(company_id=company_id, status=True)
        .filter(Product.archived_at.is_(None))
        .order_by(Product.id.asc())
        .all()
    )
    applied = 0
    initialized = 0
    skipped = []

    try:
        for product in products:
            base = product.base_uom
            if base is None:
                product.base_uom_id = selected.id
                product.sale_uom_id = selected.id
                if product.purchase_uom_id is None:
                    product.purchase_uom_id = selected.id
                initialized += 1
                applied += 1
                continue

            if base.category != selected.category:
                skipped.append(product.name)
                continue

            conversion = ProductUomConversion.query.filter_by(
                company_id=company_id,
                product_id=product.id,
                uom_id=selected.id,
            ).first()
            if conversion is not None:
                conversion.allow_sale = True

            product.sale_uom_id = selected.id
            applied += 1

        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception('No se pudo aplicar la unidad %s al catálogo de empresa %s', selected.id, company_id)
        flash('No se pudo actualizar el catálogo. No se guardaron cambios.', 'danger')
        return redirect(url_for('retail_bp.catalog_setup'))

    if skipped:
        preview = ', '.join(skipped[:3])
        suffix = '…' if len(skipped) > 3 else ''
        flash(
            f'{selected.name} se aplicó a {applied} producto(s). '
            f'{len(skipped)} se omitieron porque usan otra categoría de medida ({preview}{suffix}).',
            'warning',
        )
    else:
        extra = f' {initialized} producto(s) también recibieron su unidad base inicial.' if initialized else ''
        flash(f'{selected.name} se aplicó a los {applied} producto(s) activos.{extra}', 'success')
    return redirect(url_for('retail_bp.catalog_setup'))


@retail_bp.post('/uom')
def uom_create():
    company_id, _ = _ctx()
    try:
        factor = positive_quantity(request.form.get('factor_to_reference') or 1, 'Factor', fractional=True, places=6)
        rounding = positive_quantity(request.form.get('rounding') or 1, 'Redondeo', fractional=True, places=6)
    except BusinessRuleError as exc:
        flash(str(exc), 'danger'); return redirect(url_for('retail_bp.catalog_setup'))
    name = (request.form.get('name') or '').strip()
    symbol = (request.form.get('symbol') or '').strip()
    category = _slug(request.form.get('category') or 'UNIT')[:40]
    if not name or not symbol:
        flash('Nombre y símbolo de la unidad son obligatorios.', 'danger'); return redirect(url_for('retail_bp.catalog_setup'))
    db.session.add(UnitOfMeasure(company_id=company_id, name=name, symbol=symbol, category=category,
                                 factor_to_reference=factor, rounding=rounding,
                                 allow_fraction=request.form.get('allow_fraction') == '1'))
    try:
        db.session.commit(); flash('Unidad de medida creada.', 'success')
    except IntegrityError:
        db.session.rollback(); flash('Esa unidad ya existe en la categoría indicada.', 'danger')
    return redirect(url_for('retail_bp.catalog_setup'))


@retail_bp.post('/product/<int:product_id>/uom-conversions')
def product_uom_conversion_save(product_id):
    company_id, _ = _ctx()
    product = Product.query.filter_by(id=product_id, company_id=company_id).first_or_404()
    uom = UnitOfMeasure.query.filter_by(
        id=request.form.get('uom_id', type=int), company_id=company_id, active=True
    ).first_or_404()
    base = product.base_uom
    if not base:
        flash('Define primero la unidad base del producto.', 'warning')
        return _redirect_product(product.id)
    if uom.category != base.category:
        flash('La unidad debe pertenecer a la misma categoría que la unidad base.', 'danger')
        return _redirect_product(product.id)
    if uom.id == base.id:
        flash('La unidad base siempre equivale a 1 y no necesita una conversión.', 'info')
        return _redirect_product(product.id)
    try:
        factor = positive_quantity(request.form.get('factor_to_base'), 'Factor de conversión', fractional=True, places=6)
    except BusinessRuleError as exc:
        flash(str(exc), 'danger')
        return _redirect_product(product.id)
    row = ProductUomConversion.query.filter_by(
        company_id=company_id, product_id=product.id, uom_id=uom.id
    ).first()
    if not row:
        row = ProductUomConversion(company_id=company_id, product_id=product.id, uom_id=uom.id)
        db.session.add(row)
    row.factor_to_base = factor
    row.allow_sale = request.form.get('allow_sale') == '1'
    row.allow_purchase = request.form.get('allow_purchase') == '1'
    if not row.allow_sale and product.sale_uom_id == uom.id:
        flash('Esta unidad es la unidad de venta actual; debe permanecer habilitada para venta.', 'danger')
        db.session.rollback()
        return _redirect_product(product.id)
    if not row.allow_purchase and product.purchase_uom_id == uom.id:
        flash('Esta unidad es la unidad de compra actual; debe permanecer habilitada para compra.', 'danger')
        db.session.rollback()
        return _redirect_product(product.id)
    db.session.commit()
    flash(f'Conversión guardada: 1 {uom.symbol} = {factor} {base.symbol}.', 'success')
    return _redirect_product(product.id)


@retail_bp.post('/product/<int:product_id>/uom-conversions/<int:conversion_id>/delete')
def product_uom_conversion_delete(product_id, conversion_id):
    company_id, _ = _ctx()
    product = Product.query.filter_by(id=product_id, company_id=company_id).first_or_404()
    row = ProductUomConversion.query.filter_by(
        id=conversion_id, company_id=company_id, product_id=product.id
    ).first_or_404()
    if product.sale_uom_id == row.uom_id or product.purchase_uom_id == row.uom_id:
        flash('No puedes eliminar la conversión mientras esa unidad sea la predeterminada de venta o compra.', 'warning')
        return _redirect_product(product.id)
    db.session.delete(row)
    db.session.commit()
    flash('Conversión eliminada.', 'info')
    return _redirect_product(product.id)


@retail_bp.post('/price-lists')
def price_list_create():
    company_id, _ = _ctx()
    name = (request.form.get('name') or '').strip()
    code = _slug(request.form.get('code') or name)[:30]
    if not name:
        flash('Indica un nombre para la lista de precios.', 'danger'); return redirect(url_for('retail_bp.pricing'))
    if request.form.get('is_default') == '1':
        PriceList.query.filter_by(company_id=company_id).update({'is_default': False})
    db.session.add(PriceList(company_id=company_id, code=code, name=name,
                             currency_code=(request.form.get('currency_code') or 'DOP').upper()[:3],
                             is_default=request.form.get('is_default') == '1'))
    try:
        db.session.commit(); flash('Lista de precios creada.', 'success')
    except IntegrityError:
        db.session.rollback(); flash('Ese código de lista ya existe.', 'danger')
    return redirect(url_for('retail_bp.pricing'))


@retail_bp.post('/price-lists/<int:price_list_id>/rules')
def price_rule_create(price_list_id):
    company_id, _ = _ctx()
    price_list = PriceList.query.filter_by(id=price_list_id, company_id=company_id).first_or_404()
    try:
        product_id = _optional_tenant_id(request.form.get('product_id'), 'Producto')
        variant_id = _optional_tenant_id(request.form.get('variant_id'), 'Variante')
        category_id = _optional_tenant_id(request.form.get('category_id'), 'Categoría')

        product_row = None
        if product_id:
            product_row = Product.query.filter_by(id=product_id, company_id=company_id).filter(
                Product.archived_at.is_(None)
            ).first()
            if not product_row:
                raise BusinessRuleError('El producto seleccionado no pertenece a esta empresa.')
        variant_row = None
        if variant_id:
            variant_row = ProductVariant.query.filter_by(id=variant_id, company_id=company_id, active=True).first()
            if not variant_row:
                raise BusinessRuleError('La variante seleccionada no pertenece a esta empresa.')
            if product_row and variant_row.product_id != product_row.id:
                raise BusinessRuleError('La variante no pertenece al producto seleccionado.')
        if category_id and not Category.query.filter_by(id=category_id, company_id=company_id, status=True).first():
            raise BusinessRuleError('La categoría seleccionada no pertenece a esta empresa.')

        rule_type = (request.form.get('rule_type') or '').strip().upper()
        if rule_type not in {'FIXED', 'DISCOUNT', 'SURCHARGE'}:
            raise BusinessRuleError('Selecciona un tipo de regla de precio válido.')
        priority = finite_int(request.form.get('priority') or '10', field_name='Prioridad')
        if not 0 <= priority <= 1_000_000:
            raise BusinessRuleError('La prioridad debe estar entre 0 y 1,000,000.')
        min_qty = positive_quantity(request.form.get('min_quantity') or 1, 'Cantidad mínima', places=3)
        fixed_price = positive_money(request.form.get('fixed_price'), 'Precio fijo') if rule_type == 'FIXED' else None
        percent = (
            non_negative_quantity(request.form.get('percent') or 0, 'Porcentaje', places=3)
            if rule_type != 'FIXED' else None
        )
        if percent is not None and percent > 100:
            raise BusinessRuleError('El porcentaje debe estar entre 0 y 100.')
    except BusinessRuleError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('retail_bp.pricing'))
    db.session.add(PriceListRule(company_id=company_id, price_list_id=price_list.id, product_id=product_id,
                                 variant_id=variant_id, category_id=category_id, min_quantity=min_qty,
                                 rule_type=rule_type, fixed_price=fixed_price, percent=percent,
                                 priority=priority))
    db.session.commit(); flash('Regla de precio añadida.', 'success')
    return redirect(url_for('retail_bp.pricing'))


@retail_bp.post('/attributes')
def attribute_create():
    company_id, _ = _ctx()
    name = (request.form.get('name') or '').strip()
    if not name:
        flash('Indica el nombre del atributo.', 'danger'); return redirect(url_for('retail_bp.catalog_setup'))
    attr = ProductAttribute(company_id=company_id, name=name, display_type=(request.form.get('display_type') or 'SELECT').upper())
    db.session.add(attr)
    try:
        db.session.commit(); flash('Atributo creado.', 'success')
    except IntegrityError:
        db.session.rollback(); flash('Ese atributo ya existe.', 'danger')
    return redirect(url_for('retail_bp.catalog_setup'))


@retail_bp.post('/attributes/<int:attribute_id>/values')
def attribute_value_create(attribute_id):
    company_id, _ = _ctx()
    attr = ProductAttribute.query.filter_by(id=attribute_id, company_id=company_id).first_or_404()
    value = (request.form.get('value') or '').strip()
    if value:
        db.session.add(ProductAttributeValue(company_id=company_id, attribute_id=attr.id, value=value,
                                              color_hex=(request.form.get('color_hex') or '').strip() or None))
        try:
            db.session.commit(); flash('Valor añadido.', 'success')
        except IntegrityError:
            db.session.rollback(); flash('Ese valor ya existe.', 'warning')
    return redirect(url_for('retail_bp.catalog_setup'))


@retail_bp.post('/product/<int:product_id>/variants/generate')
def product_generate_variants(product_id):
    company_id, _ = _ctx()
    product = Product.query.filter_by(id=product_id, company_id=company_id).first_or_404()
    value_ids = [int(v) for v in request.form.getlist('attribute_value_ids') if str(v).isdigit()]
    values = ProductAttributeValue.query.filter(ProductAttributeValue.company_id == company_id, ProductAttributeValue.id.in_(value_ids)).all() if value_ids else []
    grouped = {}
    for value in values:
        grouped.setdefault(value.attribute_id, []).append(value)
    if not grouped:
        flash('Selecciona valores de atributos para generar variantes.', 'warning'); return _redirect_product(product.id)
    combinations = list(cartesian_product(*[grouped[key] for key in sorted(grouped)]))
    if len(combinations) > 150:
        flash('La combinación supera 150 variantes. Reduce los valores seleccionados.', 'danger'); return _redirect_product(product.id)
    warehouses = Warehouse.query.filter_by(company_id=company_id, status=True).all()
    created = 0
    for combo in combinations:
        suffix = '-'.join(_slug(v.value)[:12] for v in combo)
        sku = f'{product.sku}-{suffix}'[:80]
        variant = ProductVariant.query.filter_by(company_id=company_id, sku=sku).first()
        if variant:
            continue
        variant = ProductVariant(company_id=company_id, product_id=product.id, sku=sku,
                                 name=f"{product.name} / {' / '.join(v.value for v in combo)}")
        db.session.add(variant); db.session.flush()
        for value in combo:
            db.session.add(ProductVariantValue(variant_id=variant.id, attribute_value_id=value.id))
        for warehouse in warehouses:
            db.session.add(WarehouseVariantStock(company_id=company_id, warehouse_id=warehouse.id,
                                                 product_id=product.id, variant_id=variant.id, quantity=0))
        created += 1
    db.session.commit()
    flash(f'{created} variante(s) generada(s).', 'success' if created else 'info')
    return _redirect_product(product.id)


@retail_bp.post('/product/<int:product_id>/variant-stock')
def variant_stock_update(product_id):
    company_id, _ = _ctx()
    product = Product.query.filter_by(id=product_id, company_id=company_id).first_or_404()
    variant = ProductVariant.query.filter_by(id=request.form.get('variant_id', type=int), product_id=product.id, company_id=company_id).first_or_404()
    warehouse = Warehouse.query.filter_by(id=request.form.get('warehouse_id', type=int), company_id=company_id, status=True).first_or_404()
    try:
        quantity = product_quantity(request.form.get('quantity') or 0, product=product, uom=product.base_uom, allow_zero=True)
    except BusinessRuleError as exc:
        flash(str(exc), 'danger'); return _redirect_product(product.id)
    parent = WarehouseStock.query.filter_by(company_id=company_id, warehouse_id=warehouse.id, product_id=product.id).first()
    other = db.session.query(func.coalesce(func.sum(WarehouseVariantStock.quantity), 0)).filter(
        WarehouseVariantStock.company_id == company_id, WarehouseVariantStock.warehouse_id == warehouse.id,
        WarehouseVariantStock.product_id == product.id, WarehouseVariantStock.variant_id != variant.id
    ).scalar()
    if as_decimal(other) + quantity > as_decimal(parent.quantity if parent else 0):
        flash('La suma de existencias por variante no puede superar el stock total del producto en ese almacén.', 'danger')
        return _redirect_product(product.id)
    row = WarehouseVariantStock.query.filter_by(company_id=company_id, warehouse_id=warehouse.id, variant_id=variant.id).first()
    if not row:
        row = WarehouseVariantStock(company_id=company_id, warehouse_id=warehouse.id, product_id=product.id, variant_id=variant.id)
        db.session.add(row)
    row.quantity = quantity
    db.session.commit(); flash('Existencia de variante actualizada.', 'success')
    return _redirect_product(product.id)


@retail_bp.post('/product/<int:product_id>/barcodes')
def barcode_add(product_id):
    company_id, _ = _ctx()
    product = Product.query.filter_by(id=product_id, company_id=company_id).first_or_404()
    code = (request.form.get('code') or '').strip()
    variant_id = request.form.get('variant_id', type=int)
    if variant_id and not ProductVariant.query.filter_by(id=variant_id, product_id=product.id, company_id=company_id).first():
        variant_id = None
    if not code:
        flash('Escribe un código de barras.', 'danger'); return _redirect_product(product.id)
    if request.form.get('is_primary') == '1':
        ProductBarcode.query.filter_by(company_id=company_id, product_id=product.id, variant_id=variant_id).update({'is_primary': False})
    db.session.add(ProductBarcode(company_id=company_id, product_id=product.id, variant_id=variant_id,
                                  code=code, barcode_type=(request.form.get('barcode_type') or 'CODE128').upper(),
                                  is_primary=request.form.get('is_primary') == '1'))
    try:
        db.session.commit(); flash('Código añadido.', 'success')
    except IntegrityError:
        db.session.rollback(); flash('Ese código ya está asignado dentro de la empresa.', 'danger')
    return _redirect_product(product.id)


@retail_bp.post('/product/<int:product_id>/suppliers')
def supplier_link_add(product_id):
    company_id, _ = _ctx()
    product = Product.query.filter_by(id=product_id, company_id=company_id).first_or_404()
    try:
        supplier_id = tenant_id(request.form.get('supplier_id'), 'Proveedor')
        supplier = Supplier.query.filter_by(id=supplier_id, company_id=company_id, archived_at=None).first()
        if not supplier:
            raise BusinessRuleError('El proveedor seleccionado no pertenece a esta empresa.')
        variant_id = _optional_tenant_id(request.form.get('variant_id'), 'Variante')
        if variant_id and not ProductVariant.query.filter_by(
            id=variant_id, product_id=product.id, company_id=company_id, active=True,
        ).first():
            raise BusinessRuleError('La variante seleccionada no pertenece a este producto.')
        cost = positive_money(request.form.get('unit_cost') or product.cost, 'Costo')
        min_qty = product_quantity(request.form.get('min_quantity') or 1, 'Cantidad mínima', product=product, uom=product.purchase_uom or product.base_uom)
        lead_time_days = finite_int(request.form.get('lead_time_days') or '0', field_name='Días de entrega')
        if not 0 <= lead_time_days <= 3650:
            raise BusinessRuleError('Los días de entrega deben estar entre 0 y 3650.')
    except BusinessRuleError as exc:
        flash(str(exc), 'danger')
        return _redirect_product(product.id)
    if request.form.get('preferred') == '1':
        ProductSupplier.query.filter_by(company_id=company_id, product_id=product.id).update({'preferred': False})
    row = ProductSupplier.query.filter_by(company_id=company_id, product_id=product.id, variant_id=variant_id, supplier_id=supplier.id).first()
    if not row:
        row = ProductSupplier(company_id=company_id, product_id=product.id, variant_id=variant_id, supplier_id=supplier.id)
        db.session.add(row)
    row.supplier_sku = (request.form.get('supplier_sku') or '').strip() or None
    row.unit_cost = cost; row.min_quantity = min_qty; row.lead_time_days = lead_time_days
    row.preferred = request.form.get('preferred') == '1'
    db.session.commit(); flash('Proveedor del producto actualizado.', 'success')
    return _redirect_product(product.id)


@retail_bp.post('/product/<int:product_id>/bundle-items')
def bundle_item_add(product_id):
    company_id, _ = _ctx()
    bundle = Product.query.filter_by(id=product_id, company_id=company_id).first_or_404()
    component = Product.query.filter_by(id=request.form.get('component_product_id', type=int), company_id=company_id, status=True).first_or_404()
    if component.id == bundle.id:
        flash('Un producto no puede contenerse a sí mismo.', 'danger'); return _redirect_product(bundle.id)
    if getattr(component, 'tracking', 'NONE') != 'NONE':
        flash('Los componentes con lotes o series se venden como líneas individuales para conservar trazabilidad.', 'danger'); return _redirect_product(bundle.id)
    try:
        qty = product_quantity(request.form.get('quantity') or 1, product=component, uom=component.base_uom)
    except BusinessRuleError as exc:
        flash(str(exc), 'danger'); return _redirect_product(bundle.id)
    variant_id = request.form.get('component_variant_id', type=int)
    if variant_id and not ProductVariant.query.filter_by(id=variant_id, product_id=component.id, company_id=company_id).first():
        variant_id = None
    row = ProductBundleItem.query.filter_by(bundle_product_id=bundle.id, component_product_id=component.id, component_variant_id=variant_id).first()
    if row: row.quantity = qty
    else: db.session.add(ProductBundleItem(company_id=company_id, bundle_product_id=bundle.id, component_product_id=component.id, component_variant_id=variant_id, quantity=qty))
    db.session.commit(); flash('Componente del kit actualizado.', 'success')
    return _redirect_product(bundle.id)


@retail_bp.post('/product/<int:product_id>/lots')
def lot_add(product_id):
    company_id, _ = _ctx()
    product = Product.query.filter_by(id=product_id, company_id=company_id).first_or_404()
    warehouse = Warehouse.query.filter_by(id=request.form.get('warehouse_id', type=int), company_id=company_id, status=True).first_or_404()
    variant_id = request.form.get('variant_id', type=int)
    if variant_id and not ProductVariant.query.filter_by(id=variant_id, product_id=product.id, company_id=company_id).first(): variant_id = None
    lot_number = (request.form.get('lot_number') or '').strip()
    try:
        qty = product_quantity(request.form.get('quantity') or 0, product=product, uom=product.base_uom)
    except BusinessRuleError as exc:
        flash(str(exc), 'danger'); return _redirect_product(product.id)
    if not lot_number:
        flash('Indica el número de lote.', 'danger'); return _redirect_product(product.id)
    manufactured_at = None
    expires_at = None
    try:
        manufactured_at = datetime.strptime(request.form.get('manufactured_at'), '%Y-%m-%d').date() if request.form.get('manufactured_at') else None
        expires_at = datetime.strptime(request.form.get('expires_at'), '%Y-%m-%d').date() if request.form.get('expires_at') else None
    except ValueError:
        flash('La fecha de fabricación o vencimiento no es válida.', 'danger'); return _redirect_product(product.id)
    if manufactured_at and expires_at and manufactured_at > expires_at:
        flash('La fecha de fabricación no puede ser posterior al vencimiento.', 'danger'); return _redirect_product(product.id)
    row = InventoryLot.query.filter_by(company_id=company_id, product_id=product.id, variant_id=variant_id,
                                        warehouse_id=warehouse.id, lot_number=lot_number).first()
    if not row:
        row = InventoryLot(company_id=company_id, product_id=product.id, variant_id=variant_id, warehouse_id=warehouse.id,
                           lot_number=lot_number, quantity=0, manufactured_at=manufactured_at, expires_at=expires_at)
        db.session.add(row)
    row.quantity = as_decimal(row.quantity) + qty
    row.manufactured_at = manufactured_at
    row.expires_at = expires_at
    row.status = 'AVAILABLE'
    stock = WarehouseStock.query.filter_by(company_id=company_id, product_id=product.id, warehouse_id=warehouse.id).with_for_update().first()
    if not stock:
        stock = WarehouseStock(company_id=company_id, product_id=product.id, warehouse_id=warehouse.id, quantity=0); db.session.add(stock)
    stock.quantity = as_decimal(stock.quantity) + qty
    if variant_id:
        vs = WarehouseVariantStock.query.filter_by(company_id=company_id, variant_id=variant_id, warehouse_id=warehouse.id).first()
        if not vs:
            vs = WarehouseVariantStock(company_id=company_id, product_id=product.id, variant_id=variant_id, warehouse_id=warehouse.id, quantity=0); db.session.add(vs)
        vs.quantity = as_decimal(vs.quantity) + qty
    db.session.add(StockMovement(company_id=company_id, user_id=session.get('user_id'), product_id=product.id, warehouse_id=warehouse.id, movement_type='IN', quantity=qty, reason=f'Lote {lot_number}'))
    db.session.commit(); flash('Lote recibido e inventario actualizado.', 'success')
    return _redirect_product(product.id)


@retail_bp.post('/product/<int:product_id>/serials')
def serials_add(product_id):
    company_id, _ = _ctx()
    product = Product.query.filter_by(id=product_id, company_id=company_id).first_or_404()
    warehouse = Warehouse.query.filter_by(id=request.form.get('warehouse_id', type=int), company_id=company_id, status=True).first_or_404()
    variant_id = request.form.get('variant_id', type=int)
    if variant_id and not ProductVariant.query.filter_by(id=variant_id, product_id=product.id, company_id=company_id).first(): variant_id = None
    values = []
    for line in (request.form.get('serial_numbers') or '').replace(',', '\n').splitlines():
        serial = line.strip()
        if serial and serial not in values: values.append(serial)
    if not values:
        flash('Escribe al menos un serial/IMEI.', 'danger'); return _redirect_product(product.id)
    existing = {row.serial_number for row in InventorySerial.query.filter(InventorySerial.company_id == company_id, InventorySerial.serial_number.in_(values)).all()}
    new_values = [value for value in values if value not in existing]
    for value in new_values:
        serial = InventorySerial(company_id=company_id, product_id=product.id, variant_id=variant_id,
                                 warehouse_id=warehouse.id, serial_number=value, status='AVAILABLE')
        db.session.add(serial)
        db.session.flush()
        db.session.add(InventorySerialEvent(
            company_id=company_id, serial_id=serial.id, event_type='RECEIVED', warehouse_id=warehouse.id,
            notes='Alta manual de serial/IMEI',
        ))
    qty = finite_decimal(len(new_values))
    if qty:
        stock = WarehouseStock.query.filter_by(company_id=company_id, product_id=product.id, warehouse_id=warehouse.id).with_for_update().first()
        if not stock:
            stock = WarehouseStock(company_id=company_id, product_id=product.id, warehouse_id=warehouse.id, quantity=0); db.session.add(stock)
        stock.quantity = as_decimal(stock.quantity) + qty
        if variant_id:
            vs = WarehouseVariantStock.query.filter_by(company_id=company_id, variant_id=variant_id, warehouse_id=warehouse.id).first()
            if not vs:
                vs = WarehouseVariantStock(company_id=company_id, product_id=product.id, variant_id=variant_id, warehouse_id=warehouse.id, quantity=0); db.session.add(vs)
            vs.quantity = as_decimal(vs.quantity) + qty
        db.session.add(StockMovement(company_id=company_id, user_id=session.get('user_id'), product_id=product.id, warehouse_id=warehouse.id,
                                     movement_type='IN', quantity=qty, reason='Alta de seriales/IMEI'))
    db.session.commit(); flash(f'{len(new_values)} serial(es) añadidos. {len(existing)} ya existían.', 'success')
    return _redirect_product(product.id)


@retail_bp.post('/condition-stock/<int:row_id>/<action>')
def condition_stock_action(row_id, action):
    company_id, _ = _ctx()
    row = InventoryConditionStock.query.filter_by(id=row_id, company_id=company_id).with_for_update().first_or_404()
    action = (action or '').lower()
    if action not in {'release', 'scrap'}:
        flash('Acción de calidad no válida.', 'danger')
        return _redirect_product(row.product_id)
    if getattr(row.product, 'tracking', 'NONE') in {'LOT', 'SERIAL'}:
        flash('El stock trazado por lote/serie debe liberarse desde su trazabilidad específica para conservar el historial.', 'warning')
        return _redirect_product(row.product_id)
    try:
        quantity = product_quantity(request.form.get('quantity'), 'Cantidad', product=row.product, uom=row.product.base_uom)
    except BusinessRuleError as exc:
        flash(str(exc), 'danger')
        return _redirect_product(row.product_id)
    available = as_decimal(row.quantity)
    if quantity > available:
        flash(f'La cantidad supera el stock {row.condition.lower()} disponible ({available}).', 'danger')
        return _redirect_product(row.product_id)
    if action == 'release':
        if row.condition != 'QUARANTINE':
            flash('Solo el stock en cuarentena puede liberarse a disponible. El material dañado debe descartarse.', 'warning')
            return _redirect_product(row.product_id)
        stock = WarehouseStock.query.filter_by(company_id=company_id, product_id=row.product_id, warehouse_id=row.warehouse_id).with_for_update().first()
        if not stock:
            stock = WarehouseStock(company_id=company_id, product_id=row.product_id, warehouse_id=row.warehouse_id, quantity=0)
            db.session.add(stock)
        stock.quantity = as_decimal(stock.quantity) + quantity
        if row.variant_id:
            variant_stock = WarehouseVariantStock.query.filter_by(company_id=company_id, variant_id=row.variant_id, warehouse_id=row.warehouse_id).with_for_update().first()
            if not variant_stock:
                variant_stock = WarehouseVariantStock(company_id=company_id, product_id=row.product_id, variant_id=row.variant_id, warehouse_id=row.warehouse_id, quantity=0)
                db.session.add(variant_stock)
            variant_stock.quantity = as_decimal(variant_stock.quantity) + quantity
        db.session.add(StockMovement(company_id=company_id, user_id=session.get('user_id'), product_id=row.product_id, warehouse_id=row.warehouse_id, movement_type='IN', quantity=quantity, reason='Liberación de cuarentena'))
        message = f'{quantity} liberado(s) de cuarentena a stock disponible.'
    else:
        db.session.add(StockMovement(company_id=company_id, user_id=session.get('user_id'), product_id=row.product_id, warehouse_id=row.warehouse_id, movement_type='OUT', quantity=quantity, reason=f'Descarte de stock {row.condition.lower()}'))
        message = f'{quantity} unidad(es) retiradas del stock {row.condition.lower()}.'
    row.quantity = available - quantity
    db.session.commit()
    flash(message, 'success')
    return _redirect_product(row.product_id)


def _condition_stock_row(company_id, return_item, condition):
    return InventoryConditionStock.query.filter_by(
        company_id=company_id, warehouse_id=return_item.warehouse_id,
        product_id=return_item.product_id, variant_id=return_item.variant_id, condition=condition,
    ).with_for_update().first()


def _decrease_condition_stock(company_id, return_item, condition, quantity):
    row = _condition_stock_row(company_id, return_item, condition)
    if not row or as_decimal(row.quantity) < as_decimal(quantity):
        raise BusinessRuleError('El stock de calidad no coincide con la trazabilidad de la devolución. Ejecuta la validación de integridad antes de continuar.')
    row.quantity = as_decimal(row.quantity) - as_decimal(quantity)
    return row


def _quality_release_to_sellable(company_id, return_item, quantity, reason):
    stock = WarehouseStock.query.filter_by(
        company_id=company_id, product_id=return_item.product_id, warehouse_id=return_item.warehouse_id
    ).with_for_update().first()
    if not stock:
        stock = WarehouseStock(company_id=company_id, product_id=return_item.product_id, warehouse_id=return_item.warehouse_id, quantity=0)
        db.session.add(stock)
    stock.quantity = as_decimal(stock.quantity) + as_decimal(quantity)
    if return_item.variant_id:
        variant_stock = WarehouseVariantStock.query.filter_by(
            company_id=company_id, variant_id=return_item.variant_id, warehouse_id=return_item.warehouse_id
        ).with_for_update().first()
        if not variant_stock:
            variant_stock = WarehouseVariantStock(
                company_id=company_id, product_id=return_item.product_id, variant_id=return_item.variant_id,
                warehouse_id=return_item.warehouse_id, quantity=0,
            )
            db.session.add(variant_stock)
        variant_stock.quantity = as_decimal(variant_stock.quantity) + as_decimal(quantity)
    db.session.add(StockMovement(
        company_id=company_id, user_id=session.get('user_id'), product_id=return_item.product_id, warehouse_id=return_item.warehouse_id,
        movement_type='IN', quantity=quantity, reason=reason[:255],
    ))


@retail_bp.get('/quality')
def quality_center():
    company_id, user = _ctx()
    if not company_id:
        return redirect(url_for('login_bp.login'))
    condition_rows = InventoryConditionStock.query.filter(
        InventoryConditionStock.company_id == company_id, InventoryConditionStock.quantity > 0
    ).order_by(InventoryConditionStock.condition.asc(), InventoryConditionStock.updated_at.desc()).all()
    lot_rows = SaleReturnItemLotAllocation.query.filter(
        SaleReturnItemLotAllocation.company_id == company_id,
        SaleReturnItemLotAllocation.disposition.in_(['QUARANTINE','DAMAGED']),
    ).order_by(SaleReturnItemLotAllocation.created_at.asc()).limit(250).all()
    serial_rows = SaleReturnItemSerial.query.filter(
        SaleReturnItemSerial.company_id == company_id,
        SaleReturnItemSerial.disposition.in_(['QUARANTINE','DAMAGED']),
    ).order_by(SaleReturnItemSerial.created_at.asc()).limit(250).all()
    metrics = {
        'quarantine': sum((as_decimal(r.quantity) for r in condition_rows if r.condition == 'QUARANTINE'), finite_decimal('0')),
        'damaged': sum((as_decimal(r.quantity) for r in condition_rows if r.condition == 'DAMAGED'), finite_decimal('0')),
        'tracked': len(lot_rows) + len(serial_rows),
    }
    return render_template('retail/quality.html', user=user, condition_rows=condition_rows, lot_rows=lot_rows, serial_rows=serial_rows, metrics=metrics)


@retail_bp.post('/quality/lots/<int:row_id>/<action>')
def quality_lot_action(row_id, action):
    company_id, _ = _ctx()
    row = SaleReturnItemLotAllocation.query.filter_by(id=row_id, company_id=company_id).with_for_update().first_or_404()
    if row.disposition not in {'QUARANTINE','DAMAGED'}:
        flash('Este lote ya fue resuelto.', 'info')
        return redirect(url_for('retail_bp.quality_center'))
    action = (action or '').lower()
    if action not in {'release','scrap'}:
        flash('Acción de calidad no válida.', 'danger')
        return redirect(url_for('retail_bp.quality_center'))
    try:
        current_condition = row.disposition
        return_item = row.return_item
        if action == 'release':
            if current_condition != 'QUARANTINE':
                raise BusinessRuleError('El material marcado como dañado no puede volver a Disponible; debe descartarse.')
            if row.lot.expires_at and row.lot.expires_at < date.today():
                raise BusinessRuleError(f'El lote {row.lot.lot_number} está vencido y no puede liberarse a Disponible.')
            _decrease_condition_stock(company_id, return_item, current_condition, row.quantity)
            row.lot.quantity = as_decimal(row.lot.quantity) + as_decimal(row.quantity)
            row.lot.status = 'AVAILABLE'
            _quality_release_to_sellable(company_id, return_item, row.quantity, f'Liberación QC lote {row.lot.lot_number}')
            row.disposition = 'AVAILABLE'
            message = f'Lote {row.lot.lot_number} liberado a stock disponible.'
        else:
            _decrease_condition_stock(company_id, return_item, current_condition, row.quantity)
            row.disposition = 'NONE'
            db.session.add(StockMovement(
                company_id=company_id, user_id=session.get('user_id'), product_id=return_item.product_id, warehouse_id=return_item.warehouse_id,
                movement_type='OUT', quantity=row.quantity, reason=f'Descarte QC lote {row.lot.lot_number}',
            ))
            message = f'Lote {row.lot.lot_number} descartado del stock físico utilizable.'
        db.session.commit()
        flash(message, 'success')
    except BusinessRuleError as exc:
        db.session.rollback(); flash(str(exc), 'danger')
    return redirect(url_for('retail_bp.quality_center'))


@retail_bp.post('/quality/serials/<int:row_id>/<action>')
def quality_serial_action(row_id, action):
    company_id, _ = _ctx()
    row = SaleReturnItemSerial.query.filter_by(id=row_id, company_id=company_id).with_for_update().first_or_404()
    if row.disposition not in {'QUARANTINE','DAMAGED'}:
        flash('Este serial ya fue resuelto.', 'info')
        return redirect(url_for('retail_bp.quality_center'))
    action = (action or '').lower()
    if action not in {'release','scrap'}:
        flash('Acción de calidad no válida.', 'danger')
        return redirect(url_for('retail_bp.quality_center'))
    try:
        current_condition = row.disposition
        return_item = row.return_item
        serial = InventorySerial.query.filter_by(id=row.serial_id, company_id=company_id).with_for_update().first_or_404()
        if action == 'release':
            if current_condition != 'QUARANTINE':
                raise BusinessRuleError('Un serial marcado como dañado no puede volver a Disponible; debe descartarse.')
            _decrease_condition_stock(company_id, return_item, current_condition, finite_decimal('1'))
            _quality_release_to_sellable(company_id, return_item, finite_decimal('1'), f'Liberación QC serial {serial.serial_number}')
            serial.status = 'AVAILABLE'
            serial.sale_item_id = None
            serial.sold_at = None
            serial.warranty_until = None
            row.disposition = 'AVAILABLE'
            note = 'Liberado de cuarentena a inventario disponible'
        else:
            _decrease_condition_stock(company_id, return_item, current_condition, finite_decimal('1'))
            serial.status = 'SCRAPPED'
            row.disposition = 'NONE'
            db.session.add(StockMovement(
                company_id=company_id, user_id=session.get('user_id'), product_id=return_item.product_id, warehouse_id=return_item.warehouse_id,
                movement_type='OUT', quantity=finite_decimal('1'), reason=f'Descarte QC serial {serial.serial_number}',
            ))
            note = 'Descartado por control de calidad'
        db.session.add(InventorySerialEvent(
            company_id=company_id, serial_id=serial.id, event_type='ADJUSTED', return_item_id=row.return_item_id,
            warehouse_id=return_item.warehouse_id, notes=note,
        ))
        db.session.commit()
        flash(f'{serial.serial_number}: {note}.', 'success')
    except BusinessRuleError as exc:
        db.session.rollback(); flash(str(exc), 'danger')
    return redirect(url_for('retail_bp.quality_center'))


@retail_bp.get('/warranties')
def warranties():
    company_id, user = _ctx()
    if not company_id:
        return redirect(url_for('login_bp.login'))
    status = (request.args.get('status') or '').strip().upper()
    q = (request.args.get('q') or '').strip()
    query = WarrantyClaim.query.filter_by(company_id=company_id)
    if status in {'OPEN','IN_REVIEW','APPROVED','REPAIRED','REPLACED','REJECTED','CLOSED'}:
        query = query.filter(WarrantyClaim.status == status)
    if q:
        like = f'%{q}%'
        query = query.join(SaleItem, WarrantyClaim.sale_item_id == SaleItem.id).join(Product, SaleItem.product_id == Product.id).outerjoin(
            InventorySerial, WarrantyClaim.serial_id == InventorySerial.id
        ).filter(or_(Product.name.ilike(like), Product.sku.ilike(like), InventorySerial.serial_number.ilike(like)))
    claims = query.order_by(WarrantyClaim.closed_at.is_(None).desc(), WarrantyClaim.opened_at.desc()).limit(250).all()
    counts = dict(db.session.query(WarrantyClaim.status, func.count(WarrantyClaim.id)).filter(
        WarrantyClaim.company_id == company_id
    ).group_by(WarrantyClaim.status).all())
    replacement_options = {}
    for claim in claims:
        item = claim.sale_item
        if not item or getattr(item.product, 'tracking', 'NONE') != 'SERIAL' or claim.status in {'REPAIRED','REPLACED','REJECTED','CLOSED'}:
            continue
        options = InventorySerial.query.filter_by(
            company_id=company_id, product_id=item.product_id, status='AVAILABLE'
        )
        if item.variant_id:
            options = options.filter(InventorySerial.variant_id == item.variant_id)
        else:
            options = options.filter(InventorySerial.variant_id.is_(None))
        replacement_options[claim.id] = options.order_by(InventorySerial.acquired_at.asc(), InventorySerial.id.asc()).limit(100).all()
    return render_template('retail/warranties.html', user=user, claims=claims, counts=counts, status=status, q=q, replacement_options=replacement_options)


@retail_bp.post('/warranties/open/<int:sale_item_id>')
def warranty_open(sale_item_id):
    company_id, user = _ctx()
    get_retail_settings(company_id, create=True)
    item = SaleItem.query.join(Sale, Sale.id == SaleItem.sale_id).filter(
        SaleItem.id == sale_item_id,
        Sale.company_id == company_id,
        Sale.status == 'COMPLETED',
    ).first_or_404()
    reason = (request.form.get('reason') or '').strip()
    if len(reason) < 3:
        flash('Describe el motivo de la reclamación.', 'danger')
        return redirect(request.referrer or url_for('sales_bp.sale_detail', sale_id=item.sale_id))

    serial_id = request.form.get('serial_id', type=int)
    serial = None
    if serial_id:
        serial = InventorySerial.query.filter_by(id=serial_id, company_id=company_id, product_id=item.product_id).first_or_404()
        sold_here = serial.sale_item_id == item.id or InventorySerialEvent.query.filter_by(
            company_id=company_id, serial_id=serial.id, sale_item_id=item.id, event_type='SOLD'
        ).first() is not None
        if not sold_here:
            flash('El serial seleccionado no pertenece a esta venta.', 'danger')
            return redirect(url_for('sales_bp.sale_detail', sale_id=item.sale_id))
        if serial.warranty_until and serial.warranty_until < date.today():
            flash(f'La garantía del serial venció el {serial.warranty_until.strftime("%d/%m/%Y")}.', 'warning')
            return redirect(url_for('sales_bp.sale_detail', sale_id=item.sale_id))
    else:
        warranty_days = int(getattr(item.product, 'warranty_days', 0) or 0)
        if warranty_days <= 0:
            flash('Este producto no tiene una garantía configurada.', 'warning')
            return redirect(url_for('sales_bp.sale_detail', sale_id=item.sale_id))
        warranty_until = (item.sale.created_at + timedelta(days=warranty_days)).date()
        if warranty_until < date.today():
            flash(f'La garantía de esta línea venció el {warranty_until.strftime("%d/%m/%Y")}.', 'warning')
            return redirect(url_for('sales_bp.sale_detail', sale_id=item.sale_id))

    duplicate = WarrantyClaim.query.filter(
        WarrantyClaim.company_id == company_id,
        WarrantyClaim.sale_item_id == item.id,
        WarrantyClaim.serial_id == (serial.id if serial else None),
        WarrantyClaim.status.in_(['OPEN','IN_REVIEW','APPROVED']),
    ).first()
    if duplicate:
        flash(f'Ya existe una reclamación abierta (#{duplicate.id}) para este artículo.', 'warning')
        return redirect(url_for('sales_bp.sale_detail', sale_id=item.sale_id))

    claim = WarrantyClaim(
        company_id=company_id,
        serial_id=serial.id if serial else None,
        sale_item_id=item.id,
        client_id=item.sale.client_id,
        status='OPEN',
        reason=reason[:255],
    )
    db.session.add(claim)
    db.session.flush()
    if serial:
        serial.status = 'WARRANTY'
        db.session.add(InventorySerialEvent(
            company_id=company_id, serial_id=serial.id, event_type='WARRANTY_OPEN',
            sale_item_id=item.id, warranty_claim_id=claim.id, warehouse_id=serial.warehouse_id,
            notes=reason[:255],
        ))
    db.session.commit()
    flash(f'Reclamación de garantía #{claim.id} abierta. El artículo NO volvió al stock vendible: queda en proceso de garantía. Si recibiste mercancía físicamente para inventario, usa Devoluciones y elige Disponible/Cuarentena/Dañado.', 'success')
    return redirect(url_for('sales_bp.sale_detail', sale_id=item.sale_id))


@retail_bp.post('/warranties/<int:claim_id>/<action>')
def warranty_update(claim_id, action):
    company_id, user = _ctx()
    claim = WarrantyClaim.query.filter_by(id=claim_id, company_id=company_id).with_for_update().first_or_404()
    transitions = {
        'review': 'IN_REVIEW',
        'approve': 'APPROVED',
        'repair': 'REPAIRED',
        'replace': 'REPLACED',
        'reject': 'REJECTED',
        'close': 'CLOSED',
    }
    status = transitions.get((action or '').lower())
    if not status:
        flash('Acción de garantía no válida.', 'danger')
        return redirect(url_for('retail_bp.warranties'))
    terminal_states = {'REPAIRED','REPLACED','REJECTED','CLOSED'}
    if claim.status in terminal_states:
        flash('La reclamación ya está resuelta y no puede modificarse.', 'warning')
        return redirect(url_for('retail_bp.warranties'))
    resolution = (request.form.get('resolution') or '').strip()
    if status in terminal_states and len(resolution) < 3:
        flash('Indica la resolución antes de cerrar la garantía.', 'danger')
        return redirect(url_for('retail_bp.warranties'))
    claim.status = status
    claim.resolution = resolution[:255] or claim.resolution
    claim.resolved_by = user.id if user else None
    claim.updated_at = utcnow()
    if status in terminal_states:
        claim.closed_at = utcnow()
    if claim.serial:
        replacement = None
        if status == 'REPLACED':
            replacement_id = request.form.get('replacement_serial_id', type=int)
            if not replacement_id:
                flash('Selecciona el serial/IMEI que se entregará como reemplazo.', 'danger')
                return redirect(url_for('retail_bp.warranties'))
            replacement_query = InventorySerial.query.filter_by(
                id=replacement_id, company_id=company_id, product_id=claim.sale_item.product_id, status='AVAILABLE'
            )
            if claim.sale_item.variant_id:
                replacement_query = replacement_query.filter(InventorySerial.variant_id == claim.sale_item.variant_id)
            else:
                replacement_query = replacement_query.filter(InventorySerial.variant_id.is_(None))
            replacement = replacement_query.with_for_update().first()
            if not replacement:
                flash('El serial de reemplazo ya no está disponible o no corresponde a la misma variante.', 'danger')
                return redirect(url_for('retail_bp.warranties'))
            # The replacement serial is currently part of sellable stock. Consume
            # exactly one physical unit before assigning it to the original sale.
            replacement_stock = WarehouseStock.query.filter_by(
                company_id=company_id, product_id=claim.sale_item.product_id, warehouse_id=replacement.warehouse_id
            ).with_for_update().first()
            if not replacement_stock or as_decimal(replacement_stock.quantity) < 1:
                db.session.rollback()
                flash('El serial de reemplazo no tiene stock vendible consistente en su almacén.', 'danger')
                return redirect(url_for('retail_bp.warranties'))
            replacement_stock.quantity = as_decimal(replacement_stock.quantity) - finite_decimal('1')
            if replacement.variant_id:
                replacement_variant_stock = WarehouseVariantStock.query.filter_by(
                    company_id=company_id, variant_id=replacement.variant_id, warehouse_id=replacement.warehouse_id
                ).with_for_update().first()
                if not replacement_variant_stock or as_decimal(replacement_variant_stock.quantity) < 1:
                    db.session.rollback()
                    flash('El stock de la variante del serial de reemplazo no es consistente.', 'danger')
                    return redirect(url_for('retail_bp.warranties'))
                replacement_variant_stock.quantity = as_decimal(replacement_variant_stock.quantity) - finite_decimal('1')
            db.session.add(StockMovement(
                company_id=company_id, user_id=session.get('user_id'), product_id=claim.sale_item.product_id, warehouse_id=replacement.warehouse_id,
                movement_type='OUT', quantity=finite_decimal('1'), reason=f'Reemplazo garantía #{claim.id}',
            ))
            claim.serial.status = 'SCRAPPED'
            replacement.status = 'SOLD'
            replacement.sale_item_id = claim.sale_item_id
            replacement.sold_at = utcnow()
            replacement.warranty_until = claim.serial.warranty_until
            claim.replacement_serial_id = replacement.id
            db.session.add(InventorySerialEvent(
                company_id=company_id, serial_id=replacement.id, event_type='SOLD',
                sale_item_id=claim.sale_item_id, warranty_claim_id=claim.id, warehouse_id=replacement.warehouse_id,
                notes=f'Reemplazo por garantía #{claim.id}'[:255],
            ))
        elif status in {'REPAIRED','REJECTED','CLOSED'}:
            claim.serial.status = 'SOLD'
        else:
            claim.serial.status = 'WARRANTY'
        db.session.add(InventorySerialEvent(
            company_id=company_id, serial_id=claim.serial.id, event_type='WARRANTY_UPDATE',
            sale_item_id=claim.sale_item_id, warranty_claim_id=claim.id,
            warehouse_id=claim.serial.warehouse_id,
            notes=f'{status}: {claim.resolution or "sin resolución"}'[:255],
        ))
    db.session.commit()
    stock_effect = {
        'REPAIRED': 'El artículo original sigue asociado a la venta; no se creó entrada de stock.',
        'REPLACED': 'Se descontó 1 unidad/serial de reemplazo del stock vendible y el original quedó descartado.',
        'REJECTED': 'No se creó entrada de stock; el artículo original continúa asociado a la venta.',
        'CLOSED': 'No se creó entrada automática de stock.',
        'IN_REVIEW': 'El artículo permanece fuera del stock vendible mientras se revisa la garantía.',
        'APPROVED': 'El artículo permanece fuera del stock vendible hasta resolver la garantía.',
    }.get(status, 'No se modificó el stock vendible.')
    flash(f'Garantía #{claim.id} actualizada a {status}. {stock_effect}', 'success')
    return redirect(url_for('retail_bp.warranties'))


@retail_bp.post('/gift-cards')
def gift_card_create():
    company_id, _ = _ctx()
    try:
        amount = positive_money(request.form.get('amount'), 'Saldo inicial')
    except BusinessRuleError as exc:
        flash(str(exc), 'danger'); return redirect(url_for('retail_bp.customer_programs'))
    client_id = request.form.get('client_id', type=int)
    if client_id and not Client.query.filter_by(id=client_id, company_id=company_id, archived_at=None).first(): client_id = None
    code = (request.form.get('code') or '').strip().upper() or ('GFT-' + secrets.token_hex(5).upper())
    db.session.add(GiftCard(company_id=company_id, client_id=client_id, code=code, initial_balance=amount, balance=amount))
    try:
        db.session.commit(); flash(f'Tarjeta regalo {code} creada.', 'success')
    except IntegrityError:
        db.session.rollback(); flash('Ese código de tarjeta ya existe.', 'danger')
    return redirect(url_for('retail_bp.customer_programs'))


@retail_bp.post('/layaways/from-sale/<int:sale_id>')
def layaway_create(sale_id):
    company_id, user = _ctx()
    settings = get_retail_settings(company_id, create=True)
    if not settings.enable_layaway:
        flash('Los apartados no están habilitados para esta empresa.', 'warning'); return redirect(url_for('sales_bp.create_sale'))
    sale = Sale.query.filter_by(id=sale_id, company_id=company_id).with_for_update().first_or_404()
    if sale.status not in {'PENDING','DRAFT','QUOTATION'} or not sale.client_id or not sale.items:
        flash('La venta no reúne las condiciones para convertirse en apartado.', 'danger'); return redirect(url_for('sales_bp.create_sale'))
    try:
        deposit = positive_money(request.form.get('deposit') or 0, 'Inicial') if as_decimal(request.form.get('deposit') or 0) > 0 else finite_decimal('0')
    except BusinessRuleError as exc:
        flash(str(exc), 'danger'); return redirect(url_for('sales_bp.create_sale'))
    if deposit > as_decimal(sale.total):
        flash('La inicial no puede superar el total.', 'danger'); return redirect(url_for('sales_bp.create_sale'))
    due_date = None
    try:
        due_date = datetime.strptime(request.form.get('due_date'), '%Y-%m-%d').date() if request.form.get('due_date') else None
    except ValueError:
        flash('Fecha límite inválida.', 'danger'); return redirect(url_for('sales_bp.create_sale'))
    for item in sale.items:
        if item.product.product_type == ProductType.SERVICE:
            continue
        if ProductBundleItem.query.filter_by(company_id=company_id, bundle_product_id=item.product_id).first():
            db.session.rollback(); flash('Los kits/combos no se pueden apartar hasta descomponerlos en líneas físicas.', 'danger'); return redirect(url_for('sales_bp.create_sale'))
        try:
            ensure_item_available(item, sale_id=sale.id)
        except BusinessRuleError as exc:
            db.session.rollback(); flash(str(exc), 'danger'); return redirect(url_for('sales_bp.create_sale'))
        qty = as_decimal(item.quantity) * as_decimal(item.uom_factor or 1)
        db.session.add(StockReservation(company_id=company_id, sale_item_id=item.id, product_id=item.product_id,
                                        variant_id=item.variant_id, warehouse_id=item.warehouse_id, quantity=qty))
    sale.status = 'LAYAWAY'
    layaway = Layaway(company_id=company_id, sale_id=sale.id, client_id=sale.client_id,
                      deposit_amount=deposit, balance=as_decimal(sale.total) - deposit, due_date=due_date)
    db.session.add(layaway); db.session.flush()
    if deposit > 0:
        db.session.add(LayawayPayment(company_id=company_id, layaway_id=layaway.id, user_id=user.id, amount=deposit, method='CASH'))
    if session.get('current_sale_id') == sale.id: session.pop('current_sale_id', None)
    db.session.commit(); flash(f'Apartado #{layaway.id} creado.', 'success')
    return redirect(url_for('retail_bp.customer_programs'))


@retail_bp.post('/layaways/<int:layaway_id>/pay')
def layaway_pay(layaway_id):
    company_id, user = _ctx()
    layaway = Layaway.query.filter_by(id=layaway_id, company_id=company_id, status='OPEN').with_for_update().first_or_404()
    try:
        amount = positive_money(request.form.get('amount'), 'Pago')
    except BusinessRuleError as exc:
        flash(str(exc), 'danger'); return redirect(url_for('retail_bp.customer_programs'))
    amount = min(amount, as_decimal(layaway.balance))
    if amount <= 0:
        flash('El apartado ya no tiene saldo pendiente.', 'info'); return redirect(url_for('retail_bp.customer_programs'))
    layaway.deposit_amount = as_decimal(layaway.deposit_amount) + amount
    layaway.balance = max(as_decimal(layaway.balance) - amount, finite_decimal('0'))
    method = (request.form.get('method') or 'CASH').upper()
    if method not in {'CASH','CARD','TRANSFER'}:
        method = 'CASH'
    db.session.add(LayawayPayment(company_id=company_id, layaway_id=layaway.id, user_id=user.id, amount=amount,
                                  method=method, reference=(request.form.get('reference') or '').strip() or None))
    db.session.commit(); flash('Pago aplicado. Finaliza el apartado cuando el saldo llegue a cero.' if layaway.balance <= 0 else 'Pago aplicado al apartado.', 'success')
    return redirect(url_for('retail_bp.customer_programs'))


@retail_bp.post('/layaways/<int:layaway_id>/complete')
def layaway_complete(layaway_id):
    company_id, user = _ctx()
    layaway = Layaway.query.filter_by(id=layaway_id, company_id=company_id, status='OPEN').with_for_update().first_or_404()
    if as_decimal(layaway.balance) > 0:
        flash('El apartado todavía tiene saldo pendiente.', 'warning'); return redirect(url_for('retail_bp.customer_programs'))
    sale = Sale.query.filter_by(id=layaway.sale_id, company_id=company_id, status='LAYAWAY').with_for_update().first_or_404()
    try:
        settings = get_retail_settings(company_id, create=True)
        finalize_sale_inventory_and_loyalty(sale, settings=settings)
        sale.status = 'COMPLETED'; sale.amount_paid = sale.total; sale.balance = finite_decimal('0.00'); sale.payment_method = 'LAYAWAY'; sale.created_at = utcnow()
        for payment in layaway.payments:
            method = payment.method if payment.method in {'CASH','CARD','TRANSFER'} else 'OTHER'
            db.session.add(SalePayment(company_id=company_id, sale_id=sale.id, method=method, amount=payment.amount, reference=payment.reference))
        layaway.status = 'COMPLETED'; layaway.completed_at = utcnow()
        db.session.commit()
        emit_event(company_id, 'sale.completed', {'sale_id': sale.id, 'total': str(sale.total), 'client_id': sale.client_id, 'source': 'layaway'})
        flash(f'Apartado #{layaway.id} entregado y convertido en venta.', 'success')
        return redirect(url_for('sales_bp.sale_detail', sale_id=sale.id))
    except BusinessRuleError as exc:
        db.session.rollback(); flash(str(exc), 'danger'); return redirect(url_for('retail_bp.customer_programs'))


@retail_bp.post('/layaways/<int:layaway_id>/cancel')
def layaway_cancel(layaway_id):
    company_id, _ = _ctx()
    layaway = Layaway.query.filter_by(id=layaway_id, company_id=company_id, status='OPEN').with_for_update().first_or_404()
    if as_decimal(layaway.deposit_amount) > 0 and request.form.get('confirm_refund') != '1':
        flash('Este apartado tiene pagos. Confirma que el reembolso/ajuste fue gestionado antes de cancelarlo.', 'warning'); return redirect(url_for('retail_bp.customer_programs'))
    sale = Sale.query.filter_by(id=layaway.sale_id, company_id=company_id).first_or_404()
    for reservation in StockReservation.query.join(SaleItem, StockReservation.sale_item_id == SaleItem.id).filter(
        StockReservation.company_id == company_id, SaleItem.sale_id == sale.id, StockReservation.status == 'ACTIVE'
    ).all(): reservation.status = 'RELEASED'
    for item in sale.items: release_serials_for_item(item)
    layaway.status = 'CANCELLED'; sale.status = 'CANCELLED'
    db.session.commit(); flash(f'Apartado #{layaway.id} cancelado y stock liberado.', 'info')
    return redirect(url_for('retail_bp.customer_programs'))


@retail_bp.post('/approval-rules')
def approval_rule_create():
    company_id, _ = _ctx()
    try:
        threshold = bounded_decimal(
            request.form.get('threshold_amount') or 0,
            field_name='Umbral', places=2, minimum='0', maximum='9999999999.99',
        )
    except BusinessRuleError as exc:
        flash(str(exc), 'danger'); return redirect(url_for('retail_bp.operations_center'))
    operation = (request.form.get('operation_type') or '').upper()
    if operation not in {'DISCOUNT','PURCHASE','STOCK_ADJUST','RETURN','EXPENSE'}:
        flash('Tipo de aprobación inválido.', 'danger'); return redirect(url_for('retail_bp.operations_center'))
    db.session.add(ApprovalRule(company_id=company_id, operation_type=operation, threshold_amount=threshold,
                                required_role=(request.form.get('required_role') or 'admin')[:40]))
    db.session.commit(); flash('Regla de aprobación creada.', 'success')
    return redirect(url_for('retail_bp.operations_center'))


@retail_bp.post('/approvals/<int:approval_id>/<decision>')
def approval_decide(approval_id, decision):
    company_id, user = _ctx()
    row = ApprovalRequest.query.filter_by(id=approval_id, company_id=company_id, status='PENDING').first_or_404()
    if decision not in {'approve','reject'}:
        return redirect(url_for('retail_bp.operations_center'))
    row.status = 'APPROVED' if decision == 'approve' else 'REJECTED'; row.approved_by = user.id; row.resolved_at = utcnow()
    db.session.commit(); flash(f'Solicitud {row.status.lower()}.', 'success' if row.status == 'APPROVED' else 'info')
    return redirect(url_for('retail_bp.operations_center'))


@retail_bp.post('/api-keys')
def api_key_create():
    company_id, _ = _ctx()
    raw, prefix, digest = ApiKey.generate_secret()
    scopes = (request.form.get('scopes') or 'products:read,inventory:read').strip()[:500]
    db.session.add(ApiKey(company_id=company_id, name=(request.form.get('name') or 'Integración')[:100],
                          key_prefix=prefix, key_hash=digest, scopes=scopes))
    db.session.commit(); session['generated_api_key'] = raw
    flash('API key creada. Cópiala ahora: por seguridad no se volverá a mostrar.', 'success')
    return redirect(url_for('retail_bp.integrations'))


@retail_bp.post('/api-keys/<int:key_id>/revoke')
def api_key_revoke(key_id):
    company_id, _ = _ctx()
    row = ApiKey.query.filter_by(id=key_id, company_id=company_id).first_or_404(); row.active = False; db.session.commit()
    flash('API key revocada.', 'info'); return redirect(url_for('retail_bp.integrations'))


@retail_bp.post('/webhooks')
def webhook_create():
    company_id, _ = _ctx()
    name = (request.form.get('name') or '').strip()[:100]
    secret = (request.form.get('secret') or '').strip()[:120] or secrets.token_urlsafe(32)
    events = (request.form.get('event_types') or 'sale.completed').strip()[:500]
    try:
        target_url = validate_webhook_url(request.form.get('target_url') or '')
    except ValueError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('retail_bp.integrations'))
    if not name:
        flash('Indica un nombre para el webhook.', 'danger')
        return redirect(url_for('retail_bp.integrations'))
    db.session.add(OutboundWebhook(company_id=company_id, name=name, target_url=target_url, secret=secret, event_types=events))
    db.session.commit()
    flash('Webhook HTTPS creado. Firma: X-OrbisERP-Signature (HMAC-SHA256).', 'success')
    return redirect(url_for('retail_bp.integrations'))


@retail_bp.post('/replenishment/create-purchase')
def replenishment_create_purchase():
    company_id, user = _ctx()
    if not user or not all(
        user.has_permission(permission)
        for permission in ('inventory.replenishment', 'purchases.create')
    ):
        abort(403)

    supplier_id = request.form.get('supplier_id', type=int)
    supplier = Supplier.query.filter_by(id=supplier_id, company_id=company_id, archived_at=None).first_or_404()
    raw_selections = request.form.getlist('product_id')
    selected_ids = []
    seen_ids = set()
    for raw in raw_selections:
        try:
            product_id = int(raw)
        except (TypeError, ValueError):
            continue
        if product_id > 0 and product_id not in seen_ids:
            selected_ids.append(product_id)
            seen_ids.add(product_id)
    if not selected_ids:
        flash('Selecciona productos válidos para reponer.', 'warning')
        return redirect(url_for('retail_bp.operations_center'))
    if len(selected_ids) > 200:
        flash('Puedes generar como máximo 200 líneas por orden de reposición.', 'danger')
        return redirect(url_for('retail_bp.operations_center'))

    products = (
        Product.query.options(
            joinedload(Product.base_uom),
            joinedload(Product.purchase_uom),
        )
        .filter(
            Product.company_id == company_id,
            Product.id.in_(selected_ids),
            Product.status.is_(True),
            Product.archived_at.is_(None),
            Product.product_type != ProductType.SERVICE,
        )
        .all()
    )
    products_by_id = {product.id: product for product in products}

    links = (
        ProductSupplier.query.filter(
            ProductSupplier.company_id == company_id,
            ProductSupplier.supplier_id == supplier.id,
            ProductSupplier.product_id.in_(products_by_id),
        )
        .order_by(
            ProductSupplier.product_id.asc(),
            ProductSupplier.preferred.desc(),
            ProductSupplier.id.asc(),
        )
        .all()
    )
    link_by_product = {}
    for link in links:
        link_by_product.setdefault(link.product_id, link)

    stock_totals = {
        product_id: as_decimal(total)
        for product_id, total in db.session.query(
            WarehouseStock.product_id,
            func.coalesce(func.sum(WarehouseStock.quantity), 0),
        )
        .filter(
            WarehouseStock.company_id == company_id,
            WarehouseStock.product_id.in_(products_by_id),
        )
        .group_by(WarehouseStock.product_id)
        .all()
    }

    purchase_uom_ids = {
        product.purchase_uom_id or product.base_uom_id
        for product in products
        if product.purchase_uom_id or product.base_uom_id
    }
    conversions = (
        ProductUomConversion.query.filter(
            ProductUomConversion.company_id == company_id,
            ProductUomConversion.product_id.in_(products_by_id),
            ProductUomConversion.uom_id.in_(purchase_uom_ids),
        ).all()
        if purchase_uom_ids else []
    )
    conversion_by_product_uom = {
        (conversion.product_id, conversion.uom_id): conversion
        for conversion in conversions
    }

    prepared_items = []
    try:
        for product_id in selected_ids:
            product = products_by_id.get(product_id)
            link = link_by_product.get(product_id)
            if not product or not link:
                continue

            current = stock_totals.get(product.id, finite_decimal('0'))
            minimum = as_decimal(product.min_stock or 0)
            target = (
                as_decimal(product.max_stock)
                if product.max_stock is not None
                else max(minimum * finite_decimal('2'), minimum + finite_decimal('1'))
            )
            needed_base = target - current
            if needed_base <= 0:
                continue

            purchase_uom = product.purchase_uom or product.base_uom
            purchase_uom_id = purchase_uom.id if purchase_uom else None
            base_uom = product.base_uom or purchase_uom
            if purchase_uom and base_uom and purchase_uom.category != base_uom.category:
                raise BusinessRuleError(
                    f'La unidad de compra de {product.name} no pertenece a su categoría base.'
                )

            if not purchase_uom or not base_uom or purchase_uom.id == base_uom.id:
                factor = finite_decimal('1')
            else:
                conversion = conversion_by_product_uom.get((product.id, purchase_uom.id))
                if conversion:
                    if not conversion.allow_purchase:
                        raise BusinessRuleError(
                            f'{purchase_uom.name} no está habilitada para comprar {product.name}.'
                        )
                    factor = as_decimal(conversion.factor_to_base)
                else:
                    selected_factor = as_decimal(purchase_uom.factor_to_reference)
                    base_factor = as_decimal(base_uom.factor_to_reference)
                    if selected_factor <= 0 or base_factor <= 0:
                        raise BusinessRuleError(
                            f'La conversión de compra de {product.name} no tiene un factor válido.'
                        )
                    factor = (selected_factor / base_factor).quantize(
                        finite_decimal('0.000001'),
                    )
            if factor <= 0:
                raise BusinessRuleError(
                    f'La conversión de compra de {product.name} debe ser mayor que cero.'
                )

            requested_units = max(
                needed_base / factor,
                as_decimal(link.min_quantity),
            )
            fractional = (
                str(product.tracking or '').upper() != 'SERIAL'
                and (
                    str(product.sale_mode or '').upper() == 'WEIGHT'
                    or bool(purchase_uom and purchase_uom.allow_fraction)
                )
            )
            quantum = finite_decimal('0.001') if fractional else finite_decimal('1')
            qty = requested_units.quantize(quantum, rounding=ROUND_CEILING)
            qty = product_quantity(
                qty,
                'Cantidad de reposición',
                product=product,
                uom=purchase_uom,
            )
            unit_cost = bounded_decimal(
                link.unit_cost,
                field_name=f'Costo de {product.name}',
                places=2,
                minimum=0,
                maximum='99999999.99',
            )
            prepared_items.append({
                'product': product,
                'link': link,
                'quantity': qty,
                'unit_cost': unit_cost,
                'uom_id': purchase_uom_id,
                'uom_factor': factor,
            })
    except BusinessRuleError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('retail_bp.operations_center'))

    if not prepared_items:
        flash('No hay productos seleccionados vinculados a ese proveedor que necesiten reposición.', 'warning')
        return redirect(url_for('retail_bp.operations_center'))

    order = PurchaseOrder(
        company_id=company_id,
        supplier_id=supplier.id,
        supplier_name=supplier.name,
        status='PENDING',
        total_items=sum((item['quantity'] for item in prepared_items), finite_decimal('0')),
        subtotal=sum(
            (item['quantity'] * item['unit_cost'] for item in prepared_items),
            finite_decimal('0.00'),
        ).quantize(finite_decimal('0.01')),
        tax_total=finite_decimal('0.00'),
    )
    order.total_cost = order.subtotal
    db.session.add(order)
    db.session.flush()
    for item in prepared_items:
        db.session.add(PurchaseOrderItem(
            purchase_order_id=order.id,
            product_id=item['product'].id,
            variant_id=item['link'].variant_id,
            quantity=item['quantity'],
            quantity_received=finite_decimal('0'),
            unit_cost=item['unit_cost'],
            uom_id=item['uom_id'],
            uom_factor=item['uom_factor'],
        ))
    db.session.commit()
    flash(f'Orden de compra #{order.id} creada desde reposición.', 'success')
    return redirect(url_for('purchase_bp.purchase_detail', order_id=order.id))
