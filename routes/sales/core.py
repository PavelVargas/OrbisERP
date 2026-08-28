from __future__ import annotations

from services.numeric import NumericValueError, finite_decimal
from decimal import Decimal

from flask import current_app, render_template, request, redirect, url_for, flash, session, jsonify, g
from sqlalchemy import or_, func

from db import db
from models.sales.sales import Sale
from models.sales.sale_item import SaleItem
from models.products.products import Product, ProductType
from models.category.category import Category
from models.client.client import Client
from models.warehouse.warehouse import Warehouse
from models.warehouse_stock.warehouse_stock import WarehouseStock
from models.stock_transfer.stock_transfer import StockTransfer
from models.user.user import User
from models.divisas.divisas import ExchangeRate
from models.productivity import Promotion, SalesTax
from models.retail import (
    ProductBarcode, ProductVariant, UnitOfMeasure, PosTerminal,
    WarehouseVariantStock, StockReservation,
)
from services.time_utils import utcnow
from services.validation import BusinessRuleError, positive_integer, tenant_id
from services.quantity import as_decimal, display_quantity, product_quantity
from services.retail import (
    resolve_sale_price, resolve_price_list, uom_to_base, product_uom_options,
    reserve_serials_for_item, release_serials_for_item, get_retail_settings,
)
from services.sale_engine import ensure_item_available

from services.product_images import product_image_url
from .sales import sales_bp
from .access import editable_sales_query


def resolve_sale_terminal(user, company_id, requested_id=None, sale=None):
    query = PosTerminal.query.filter_by(company_id=company_id, status=True)
    if user.terminal_id:
        terminal = query.filter_by(id=user.terminal_id).first()
        if not terminal:
            raise BusinessRuleError('La terminal POS asignada a esta cuenta no está activa.')
        if requested_id and int(requested_id) != terminal.id:
            raise BusinessRuleError(f'Esta cuenta está asignada a {terminal.name}.')
        return terminal
    if sale and sale.terminal_id:
        terminal = query.filter_by(id=sale.terminal_id).first()
        if terminal:
            if requested_id and int(requested_id) != terminal.id and sale.items:
                raise BusinessRuleError('Vacía el carrito antes de cambiar de terminal POS.')
            return terminal
    if requested_id:
        terminal = query.filter_by(id=int(requested_id)).first()
        if not terminal:
            raise BusinessRuleError('La terminal POS seleccionada no está disponible.')
        return terminal
    terminals = query.order_by(PosTerminal.name.asc()).all()
    return terminals[0] if len(terminals) == 1 else None


def resolve_sale_warehouse(user, company_id, requested_id=None, sale=None, terminal=None):
    """Resolve a tenant-safe, sale-locked warehouse."""
    active_query = Warehouse.query.filter_by(company_id=company_id, status=True)

    if terminal:
        if requested_id and int(requested_id) != int(terminal.warehouse_id):
            raise BusinessRuleError(f'La terminal {terminal.name} opera desde {terminal.warehouse.name}.')
        requested_id = terminal.warehouse_id

    if user.warehouse_id:
        warehouse = active_query.filter_by(id=user.warehouse_id).first()
        if not warehouse:
            raise BusinessRuleError('Tu almacén asignado no está activo o no pertenece a esta empresa.')
        if requested_id and int(requested_id) != int(warehouse.id):
            raise BusinessRuleError(f'Esta cuenta está asignada a {warehouse.name}; no puede vender desde otro almacén.')
        return warehouse

    existing_ids = []
    if sale is not None:
        existing_ids = sorted({int(item.warehouse_id) for item in sale.items if item.warehouse_id})
        if len(existing_ids) > 1:
            raise BusinessRuleError('Esta venta contiene artículos de varios almacenes y debe revisarse antes de continuar.')
        if len(existing_ids) == 1:
            warehouse = active_query.filter_by(id=existing_ids[0]).first()
            if not warehouse:
                raise BusinessRuleError('El almacén asociado a esta venta ya no está disponible.')
            if requested_id and int(requested_id) != int(warehouse.id):
                raise BusinessRuleError(f'La venta ya está vinculada a {warehouse.name}. Vacía el carrito antes de cambiar de almacén.')
            return warehouse

    if requested_id:
        warehouse = active_query.filter_by(id=int(requested_id)).first()
        if not warehouse:
            raise BusinessRuleError('El almacén seleccionado no está disponible para esta empresa.')
        return warehouse

    active = active_query.order_by(Warehouse.is_main.desc(), Warehouse.name.asc()).all()
    if len(active) == 1:
        return active[0]
    return None


def _sales_tax_for_product(product, company_id):
    tax = product.sales_tax if getattr(product, 'sales_tax_id', None) else None
    if tax and tax.company_id == company_id and tax.active:
        return tax
    return SalesTax.query.filter_by(company_id=company_id, active=True, is_default=True).first()


def _promotion_targets_item(promotion, item):
    scope = (getattr(promotion, 'scope', 'ALL') or 'ALL').upper()
    if scope == 'ALL':
        return True
    if scope == 'PRODUCT':
        return int(getattr(promotion, 'target_product_id', 0) or 0) == int(item.product_id)
    if scope == 'CATEGORY':
        return int(getattr(promotion, 'target_category_id', 0) or 0) == int(getattr(item.product, 'category_id', 0) or 0)
    if scope == 'BRAND':
        return bool(getattr(promotion, 'target_brand', None)) and (getattr(item.product, 'brand', '') or '').strip().lower() == promotion.target_brand.strip().lower()
    return False


def _item_gross_amount(item):
    line = (as_decimal(item.quantity) * as_decimal(item.price)).quantize(finite_decimal('0.01'))
    rate = as_decimal(item.tax_rate) / finite_decimal('100')
    return line if item.tax_included else (line * (finite_decimal('1') + rate)).quantize(finite_decimal('0.01'))


def _promotion_discount(sale, promotion, gross_total):
    if not promotion or promotion.company_id != sale.company_id or not promotion.is_available(subtotal=gross_total):
        return finite_decimal('0.00')
    eligible = [item for item in sale.items if _promotion_targets_item(promotion, item)]
    eligible_gross = sum((_item_gross_amount(item) for item in eligible), finite_decimal('0.00'))
    if eligible_gross <= 0:
        return finite_decimal('0.00')
    mechanic = (getattr(promotion, 'mechanic', 'STANDARD') or 'STANDARD').upper()
    if mechanic == 'BUY_X_GET_Y':
        buy = max(as_decimal(getattr(promotion, 'buy_qty', 1)), finite_decimal('0.001'))
        reward = max(as_decimal(getattr(promotion, 'reward_qty', 1)), finite_decimal('0.001'))
        group = buy + reward
        discount = finite_decimal('0.00')
        for item in eligible:
            qty = as_decimal(item.quantity)
            groups = int(qty // group)
            if groups <= 0:
                continue
            unit_gross = _item_gross_amount(item) / max(qty, finite_decimal('0.001'))
            discount += (unit_gross * reward * groups).quantize(finite_decimal('0.01'))
    elif mechanic == 'SECOND_PERCENT':
        buy = max(as_decimal(getattr(promotion, 'buy_qty', 1)), finite_decimal('0.001'))
        reward = max(as_decimal(getattr(promotion, 'reward_qty', 1)), finite_decimal('0.001'))
        percent = min(max(as_decimal(getattr(promotion, 'reward_percent', 50)), finite_decimal('0')), finite_decimal('100'))
        group = buy + reward
        discount = finite_decimal('0.00')
        for item in eligible:
            qty = as_decimal(item.quantity)
            groups = int(qty // group)
            if groups <= 0:
                continue
            unit_gross = _item_gross_amount(item) / max(qty, finite_decimal('0.001'))
            discount += (unit_gross * reward * groups * percent / finite_decimal('100')).quantize(finite_decimal('0.01'))
    elif promotion.discount_type == 'PERCENT':
        discount = (eligible_gross * as_decimal(promotion.value) / finite_decimal('100')).quantize(finite_decimal('0.01'))
    else:
        discount = min(as_decimal(promotion.value).quantize(finite_decimal('0.01')), eligible_gross)
    cap = getattr(promotion, 'max_discount', None)
    if cap is not None:
        discount = min(discount, as_decimal(cap))
    return min(max(discount, finite_decimal('0.00')), gross_total).quantize(finite_decimal('0.01'))


def recalc_sale(sale):
    """Recalculate taxes, advanced promotions and totals using Decimal end-to-end."""
    net_total = finite_decimal('0.00')
    tax_total = finite_decimal('0.00')
    gross_total = finite_decimal('0.00')
    for item in sale.items:
        line = (as_decimal(item.quantity) * as_decimal(item.price)).quantize(finite_decimal('0.01'))
        rate = as_decimal(item.tax_rate) / finite_decimal('100')
        if item.tax_included and rate > 0:
            net = (line / (finite_decimal('1') + rate)).quantize(finite_decimal('0.01'))
            tax = line - net
            gross = line
        else:
            net = line
            tax = (line * rate).quantize(finite_decimal('0.01'))
            gross = line + tax
        net_total += net
        tax_total += tax
        gross_total += gross

    promotion = sale.promotion if getattr(sale, 'promotion_id', None) else None
    discount = _promotion_discount(sale, promotion, gross_total)
    if promotion and not promotion.is_available(subtotal=gross_total):
        # Keep the relationship and FK coherent in the current transaction.
        sale.promotion = None
        sale.promotion_id = None
        discount = finite_decimal('0.00')

    sale.subtotal = net_total.quantize(finite_decimal('0.01'))
    sale.itbis = tax_total.quantize(finite_decimal('0.01'))
    sale.discount_amount = discount
    sale.total = (gross_total - discount).quantize(finite_decimal('0.01'))


def _find_catalog_entry(company_id, term):
    term = (term or '').strip()
    if not term:
        return None, None
    barcode = ProductBarcode.query.filter_by(company_id=company_id, code=term).first()
    if barcode and barcode.product and barcode.product.status and not barcode.product.archived_at:
        return barcode.product, barcode.variant
    variant = ProductVariant.query.filter_by(company_id=company_id, sku=term, active=True).first()
    if variant and variant.product and variant.product.status and not variant.product.archived_at:
        return variant.product, variant
    product = Product.query.filter_by(company_id=company_id, sku=term, status=True).filter(Product.archived_at.is_(None)).first()
    if not product:
        product = Product.query.filter_by(company_id=company_id, name=term, status=True).filter(Product.archived_at.is_(None)).first()
    return product, None


def _compatible_uoms(product):
    return product_uom_options(product, purpose='sale')


def _catalog_fallback_price(product, variant=None):
    """Return the product's direct price without applying a malformed price rule."""
    base = as_decimal(product.price)
    if variant is not None:
        base += as_decimal(variant.price_extra)
    return max(base, finite_decimal('0')).quantize(finite_decimal('0.01'))


def _set_line_price(item, sale):
    product = item.product
    if product is None:
        raise BusinessRuleError(
            'No se pudo identificar el producto de la línea. Recarga la caja y vuelve a agregarlo.'
        )
    variant = item.variant
    if variant is not None and int(variant.product_id) != int(product.id):
        raise BusinessRuleError('La variante seleccionada no pertenece al producto de la línea.')
    client = sale.client
    base_qty = as_decimal(item.quantity) * as_decimal(item.uom_factor or 1)
    unit_base_price, price_list = resolve_sale_price(
        product, quantity=base_qty, company_id=sale.company_id,
        client=client, variant=variant, price_list_id=sale.price_list_id,
    )
    item.price = (unit_base_price * as_decimal(item.uom_factor or 1)).quantize(finite_decimal('0.01'))
    # Keep the relationship and foreign key coherent during this request. Setting
    # only price_list_id can leave sale.price_list pointing at the previous list
    # until SQLAlchemy expires the object.
    sale.price_list = price_list
    sale.price_list_id = price_list.id if price_list else None


def _reprice_sale(sale):
    selected = resolve_price_list(sale.company_id, client=sale.client, explicit_id=sale.price_list_id)
    sale.price_list = selected
    sale.price_list_id = selected.id if selected else None
    for item in sale.items:
        _set_line_price(item, sale)
    recalc_sale(sale)


def _sale_cart_payload(sale):
    """Return the canonical POS cart state after a committed mutation.

    Keeping this payload on the server prevents the browser from reimplementing
    pricing, tax or promotion rules. Amounts remain in the company's base
    currency and are formatted by the already-loaded POS currency context.
    """
    if sale is None:
        raise BusinessRuleError('No hay una venta activa para actualizar el pedido.')

    items = []
    for item in sale.items:
        product = item.product
        if product is None:
            current_app.logger.error(
                'POS sale_id=%s contains line_id=%s without a product relationship',
                sale.id, item.id,
            )
            raise BusinessRuleError(
                'El pedido contiene una línea sin producto. Elimina la línea o solicita una revisión de integridad.'
            )
        variant = item.variant
        quantity = as_decimal(item.quantity)
        unit_price = as_decimal(item.price)
        line_total = (quantity * unit_price).quantize(finite_decimal('0.01'))
        unit = item.uom or getattr(product, 'base_uom', None)
        items.append({
            'id': item.id,
            'name': variant.name if variant else product.name,
            'quantity': display_quantity(quantity),
            'uom': getattr(unit, 'symbol', None) or 'ud',
            'unit_price': str(unit_price),
            'line_total': str(line_total),
            'remove_url': url_for('sales_bp.remove_item', item_id=item.id),
        })

    promotion = sale.promotion if getattr(sale, 'promotion_id', None) else None
    discount = as_decimal(sale.discount_amount or 0)
    return {
        'sale_id': sale.id,
        'items': items,
        'line_count': len(items),
        'item_count': display_quantity(sum(
            (as_decimal(item.quantity) for item in sale.items),
            finite_decimal('0'),
        )),
        'subtotal': str(as_decimal(sale.subtotal or 0)),
        'tax': str(as_decimal(sale.itbis or 0)),
        'discount': str(discount),
        'total': str(as_decimal(sale.total or 0)),
        'promotion_code': promotion.code if promotion else None,
        'has_items': bool(items),
        'has_client': bool(sale.client_id),
        'can_checkout': bool(items),
    }


def _add_line(sale, product, variant, warehouse, qty, uom_id=None):
    """Add or increase a POS line with tenant, UOM and ORM integrity checks.

    Pricing and stock checks run before the transaction is committed. A new
    ``SaleItem`` therefore needs its relationship objects immediately, not only
    its foreign-key values. The same relationships are refreshed on an existing
    line so stale identity-map state cannot reach ``resolve_sale_price``.
    """
    if sale is None or product is None or warehouse is None:
        raise BusinessRuleError('La venta, el producto y el almacén son obligatorios.')
    if int(sale.company_id) != int(product.company_id):
        raise BusinessRuleError('El producto no pertenece a la empresa de esta venta.')
    if int(sale.company_id) != int(warehouse.company_id):
        raise BusinessRuleError('El almacén no pertenece a la empresa de esta venta.')
    if not bool(getattr(product, 'status', False)) or getattr(product, 'archived_at', None) is not None:
        raise BusinessRuleError('El producto fue desactivado o archivado y ya no se puede vender.')
    if variant is not None and (
        int(variant.product_id) != int(product.id)
        or int(variant.company_id) != int(sale.company_id)
        or not variant.active
    ):
        raise BusinessRuleError('La variante seleccionada no está disponible para este producto.')

    qty = as_decimal(qty)
    if qty <= 0:
        raise BusinessRuleError('La cantidad debe ser mayor que cero.')

    selected_uom_id = uom_id or product.sale_uom_id or product.base_uom_id
    if not selected_uom_id:
        raise BusinessRuleError(
            'El producto no tiene una unidad de venta configurada. Corrígelo en Productos antes de vender.'
        )

    allowed_uoms = {
        int(unit.id): as_decimal(factor)
        for unit, factor in _compatible_uoms(product)
        if unit is not None and getattr(unit, 'id', None) is not None
    }
    if int(selected_uom_id) not in allowed_uoms:
        raise BusinessRuleError(
            'La unidad seleccionada no está habilitada para vender este producto. '
            'Actualiza el catálogo o corrige sus conversiones de unidad.'
        )

    base_qty = uom_to_base(product, qty, selected_uom_id, purpose='sale')
    factor = (base_qty / qty) if qty else finite_decimal('1')
    configured_factor = allowed_uoms[int(selected_uom_id)]
    if configured_factor <= 0 or factor <= 0:
        raise BusinessRuleError('La unidad de venta tiene un factor de conversión inválido.')

    existing = SaleItem.query.filter_by(
        sale_id=sale.id, product_id=product.id, variant_id=(variant.id if variant else None),
        warehouse_id=warehouse.id, uom_id=selected_uom_id,
    ).first()
    old_sale_price_list = getattr(sale, 'price_list', None)
    old_sale_price_list_id = getattr(sale, 'price_list_id', None)
    old_state = None
    if existing:
        old_state = {
            'quantity': existing.quantity,
            'product': existing.product,
            'product_id': existing.product_id,
            'variant': existing.variant,
            'variant_id': existing.variant_id,
            'warehouse': existing.warehouse,
            'warehouse_id': existing.warehouse_id,
            'uom_id': existing.uom_id,
            'uom_factor': existing.uom_factor,
            'price': existing.price,
        }
        existing.product = product
        existing.product_id = product.id
        existing.variant = variant
        existing.variant_id = variant.id if variant else None
        existing.warehouse = warehouse
        existing.warehouse_id = warehouse.id
        existing.uom_id = selected_uom_id
        existing.uom_factor = factor
        existing.quantity = as_decimal(existing.quantity) + qty
        item = existing
    else:
        tax = _sales_tax_for_product(product, sale.company_id)
        item = SaleItem(
            sale=sale, sale_id=sale.id,
            product=product, product_id=product.id,
            variant=variant, variant_id=variant.id if variant else None,
            warehouse=warehouse, warehouse_id=warehouse.id,
            uom_id=selected_uom_id, uom_factor=factor,
            quantity=qty, price=0,
            tax_name=tax.name if tax else 'Exento', tax_rate=tax.rate if tax else 0,
            tax_included=tax.price_included if tax else True,
        )
        db.session.add(item)
    try:
        _set_line_price(item, sale)
        if product.product_type != ProductType.SERVICE:
            ensure_item_available(item, sale_id=sale.id)
        db.session.flush()
        reserve_serials_for_item(item)
        recalc_sale(sale)
        return item
    except Exception:
        sale.price_list = old_sale_price_list
        sale.price_list_id = old_sale_price_list_id
        if existing and old_state is not None:
            for field, value in old_state.items():
                setattr(existing, field, value)
        raise


@sales_bp.route('/create', methods=['GET', 'POST'])
def create_sale():
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    if not user_id or not company_id:
        flash('Debes iniciar sesión para crear ventas', 'warning')
        return redirect(url_for('login_bp.login'))

    user = User.query.filter_by(id=user_id, company_id=company_id).first_or_404()
    from models.company.company import Company
    company = Company.query.filter_by(id=company_id).first_or_404()
    plan_limits = company.get_plan_limits()
    current_usage = company.get_current_month_usage()
    retail_settings = get_retail_settings(company_id, create=True)

    current_id = session.get('current_sale_id')
    sale = Sale.query.filter_by(id=current_id, company_id=company_id, user_id=user_id).first() if current_id else None
    if sale and sale.status not in {'PENDING', 'QUOTATION', 'DRAFT'}:
        sale = None
        session.pop('current_sale_id', None)
    if not sale:
        sale = Sale.query.filter_by(status='PENDING', user_id=user_id, company_id=company_id).first()
    if not sale:
        sale = Sale(status='PENDING', user_id=user_id, company_id=company_id, created_at=utcnow())
        db.session.add(sale)
        db.session.flush()
    session['current_sale_id'] = sale.id

    active_terminals = PosTerminal.query.filter_by(company_id=company_id, status=True).order_by(PosTerminal.name.asc()).all()
    requested_terminal_id = request.values.get('terminal_id', type=int)
    if requested_terminal_id is None and not user.terminal_id:
        requested_terminal_id = session.get('sales_terminal_id')
    try:
        sale_terminal = resolve_sale_terminal(user, company_id, requested_terminal_id, sale=sale)
        if sale_terminal:
            sale.terminal_id = sale_terminal.id
            sale.branch_id = sale_terminal.branch_id
            session['sales_terminal_id'] = sale_terminal.id
    except BusinessRuleError as exc:
        flash(str(exc), 'danger')
        sale_terminal = None
        session.pop('sales_terminal_id', None)

    active_warehouses = Warehouse.query.filter_by(company_id=company_id, status=True).order_by(Warehouse.is_main.desc(), Warehouse.name.asc()).all()
    requested_warehouse_id = request.values.get('warehouse_id', type=int)
    if requested_warehouse_id is None and not user.warehouse_id:
        requested_warehouse_id = session.get('sales_warehouse_id')
    try:
        sale_warehouse = resolve_sale_warehouse(
            user, company_id, requested_id=requested_warehouse_id,
            sale=sale, terminal=sale_terminal,
        )
        if sale_warehouse:
            session['sales_warehouse_id'] = sale_warehouse.id
            if not sale.branch_id:
                sale.branch_id = sale_warehouse.branch_id
    except BusinessRuleError as exc:
        flash(str(exc), 'danger')
        sale_warehouse = None
        session.pop('sales_warehouse_id', None)

    search_query = request.form.get('search', '').strip()
    if search_query:
        product, variant = _find_catalog_entry(company_id, search_query)
        if not product:
            flash(f'No se encontró el producto o código "{search_query}"', 'warning')
        elif not sale_warehouse:
            flash('Selecciona el almacén/terminal de origen antes de agregar productos.', 'warning')
        else:
            try:
                _add_line(sale, product, variant, sale_warehouse, finite_decimal('1'), product.sale_uom_id or product.base_uom_id)
                db.session.commit()
                flash(f'{variant.name if variant else product.name} agregado.', 'success')
            except (BusinessRuleError, NumericValueError) as exc:
                db.session.rollback(); flash(str(exc), 'danger')
            except Exception:
                db.session.rollback()
                current_app.logger.exception(
                    'Unexpected POS direct-search add failure request_id=%s company_id=%s sale_id=%s query=%r',
                    getattr(g, 'request_id', None), company_id, sale.id, search_query,
                )
                flash(
                    'No se pudo agregar el producto buscado. No se guardó ningún cambio. '
                    f'Referencia: {getattr(g, "request_id", "sin referencia")}.',
                    'danger',
                )

    selected_currency = session.get('selected_currency', 'DOP')
    rate_row = ExchangeRate.query.filter_by(currency_code=selected_currency, company_id=company_id).first()
    currency_symbol = rate_row.symbol if rate_row else 'RD$'
    conversion_rate = as_decimal(rate_row.rate if rate_row else 1)
    if conversion_rate <= 0:
        conversion_rate = finite_decimal('1')

    categories = Category.query.filter_by(company_id=company_id).order_by(Category.name.asc()).all()
    clients = Client.query.filter_by(company_id=company_id).filter(Client.archived_at.is_(None)).order_by(Client.name.asc()).all()
    db.session.commit()

    return render_template(
        'sales/create_sales.html', sale=sale, categories=categories, clients=clients, user=user,
        plan_limits=plan_limits, current_usage=current_usage,
        current_currency=selected_currency, currency_symbol=currency_symbol, conversion_rate=conversion_rate,
        warehouses=active_warehouses, sale_warehouse=sale_warehouse,
        warehouse_locked=bool(user.warehouse_id or sale.items or sale_terminal),
        terminals=active_terminals, sale_terminal=sale_terminal,
        terminal_locked=bool(user.terminal_id or sale.items), retail_settings=retail_settings,
    )


@sales_bp.route('/add/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    company_id = session.get('company_id')
    sale_id = session.get('current_sale_id')
    user_id = session.get('user_id')
    wants_json = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or 'application/json' in request.headers.get('Accept', '')
    )
    create_url = url_for('sales_bp.create_sale')

    def reject(message, status=400, category='danger', redirect_url=None):
        destination = redirect_url or create_url
        if wants_json:
            return jsonify(
                ok=False,
                error=message,
                redirect=destination,
                request_id=getattr(g, 'request_id', None),
            ), status
        flash(message, category)
        return redirect(destination)

    if not company_id or not user_id:
        return reject('Tu sesión expiró. Inicia sesión nuevamente para continuar.', 401, redirect_url=url_for('login_bp.login'))
    if not sale_id:
        session.pop('current_sale_id', None)
        return reject('No hay una venta activa. Recarga la caja para iniciar un pedido nuevo.', 409)

    sale = Sale.query.filter_by(id=sale_id, company_id=company_id).with_for_update().first()
    if not sale:
        session.pop('current_sale_id', None)
        return reject('La venta activa ya no existe. Recarga la caja para crear un pedido nuevo.', 404)
    if sale.user_id != user_id:
        return reject('No tienes permiso para modificar esta venta.', 403, redirect_url=url_for('sales_bp.list_sales'))
    if sale.status not in {'DRAFT', 'PENDING', 'QUOTATION'}:
        return reject('Esta venta ya no admite modificaciones.', 409, 'warning', url_for('sales_bp.list_sales'))

    user = User.query.filter_by(id=user_id, company_id=company_id).first()
    if not user:
        return reject('Tu usuario ya no está disponible en esta empresa.', 403, redirect_url=url_for('login_bp.logout'))
    product = Product.query.filter_by(
        id=product_id, company_id=company_id, status=True
    ).filter(Product.archived_at.is_(None)).first()
    if not product:
        return reject('El producto ya no está disponible. Actualiza el catálogo e inténtalo nuevamente.', 404, 'warning')

    variant_id = request.form.get('variant_id', type=int)
    variant = None
    if variant_id:
        variant = ProductVariant.query.filter_by(
            id=variant_id, product_id=product.id, company_id=company_id, active=True
        ).first()
        if not variant:
            return reject('La variante seleccionada ya no está disponible para este producto.', 409, 'warning')

    try:
        uom_id = request.form.get('uom_id', type=int) or product.sale_uom_id or product.base_uom_id
        selected_uom = None
        if uom_id:
            selected_uom = UnitOfMeasure.query.filter_by(
                id=uom_id, company_id=company_id, active=True
            ).first()
            if not selected_uom:
                raise BusinessRuleError('La unidad de medida seleccionada no está disponible.')
        qty = product_quantity(request.form.get('qty', 1), 'Cantidad', product=product, uom=selected_uom)
        requested_warehouse_id = tenant_id(request.form.get('warehouse_id'), 'Almacén')
        terminal = resolve_sale_terminal(user, company_id, request.form.get('terminal_id', type=int), sale=sale)
        warehouse = resolve_sale_warehouse(user, company_id, requested_id=requested_warehouse_id, sale=sale, terminal=terminal)
        if not warehouse:
            raise BusinessRuleError('Selecciona el almacén de origen antes de agregar productos.')
        item = _add_line(sale, product, variant, warehouse, qty, uom_id)
        if terminal:
            sale.terminal_id, sale.branch_id = terminal.id, terminal.branch_id
        # Build the canonical response before commit. This catches a malformed
        # in-memory cart while the transaction can still be rolled back instead
        # of committing and then failing while serializing the AJAX response.
        cart = _sale_cart_payload(sale)
        db.session.commit()
    except (BusinessRuleError, NumericValueError) as exc:
        db.session.rollback()
        return reject(str(exc), 400)
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            'Unexpected POS add failure request_id=%s company_id=%s sale_id=%s product_id=%s',
            getattr(g, 'request_id', None), company_id, sale_id, product_id,
        )
        return reject(
            'No se pudo agregar el producto por un error interno. No se guardó ningún cambio; '
            'actualiza el catálogo y vuelve a intentarlo. Si continúa, comparte la referencia mostrada.',
            500,
        )

    label = variant.name if variant else product.name
    message = f'{label} agregado al pedido.'
    if wants_json:
        return jsonify(
            ok=True,
            message=message,
            redirect=create_url,
            sale_id=sale.id,
            item_id=item.id,
            cart=cart,
        )
    flash(message, 'success')
    return redirect(create_url)


@sales_bp.route('/assign-client', methods=['POST'])
def assign_client():
    company_id = session.get('company_id')
    sale_id = session.get('current_sale_id')
    user_id = session.get('user_id')
    wants_json = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or 'application/json' in request.headers.get('Accept', '')
    )
    create_url = url_for('sales_bp.create_sale')

    def reject(message, status=400, redirect_url=None):
        destination = redirect_url or create_url
        if wants_json:
            return jsonify(
                ok=False,
                error=message,
                redirect=destination,
                request_id=getattr(g, 'request_id', None),
            ), status
        flash(message, 'danger' if status >= 400 else 'warning')
        return redirect(destination)

    if not company_id or not user_id:
        return reject(
            'Tu sesión expiró. Inicia sesión nuevamente para cambiar el cliente.',
            401,
            url_for('login_bp.login'),
        )
    if not sale_id:
        return reject('No hay una venta activa para asignar el cliente.', 409)

    sale = editable_sales_query(company_id, user_id).filter_by(id=sale_id).with_for_update().first()
    if not sale:
        session.pop('current_sale_id', None)
        return reject('La venta activa ya no existe. Recarga la caja para iniciar un pedido nuevo.', 404)
    if sale.status not in {'DRAFT', 'PENDING', 'QUOTATION'}:
        return reject(
            'Esta venta ya no admite modificaciones.',
            409,
            url_for('sales_bp.list_sales'),
        )

    client_id = request.form.get('client_id', type=int)
    client = None
    if client_id:
        client = Client.query.filter_by(id=client_id, company_id=company_id).filter(
            Client.archived_at.is_(None)
        ).first()
        if not client:
            return reject('El cliente seleccionado ya no está disponible en esta empresa.', 404)

    try:
        # Relationship assignment is intentional. Setting only client_id can
        # leave sale.client stale during _reprice_sale(), applying the previous
        # customer's price list until the following request.
        sale.client = client
        sale.client_id = client.id if client else None
        sale.price_list = None
        sale.price_list_id = client.price_list_id if client else None
        _reprice_sale(sale)
        cart = _sale_cart_payload(sale)
        price_list_name = sale.price_list.name if sale.price_list else 'precio público'
        db.session.commit()
    except (BusinessRuleError, NumericValueError) as exc:
        db.session.rollback()
        return reject(str(exc), 400)
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            'Unexpected POS client assignment failure request_id=%s company_id=%s sale_id=%s client_id=%s',
            getattr(g, 'request_id', None), company_id, sale_id, client_id,
        )
        return reject(
            'No se pudo cambiar el cliente ni recalcular los precios. No se guardó ningún cambio; '
            'recarga el pedido y vuelve a intentarlo.',
            500,
        )

    message = (
        f'Cliente "{client.name}" asignado · {price_list_name}.'
        if client else
        f'Venta configurada como cliente general · {price_list_name}.'
    )
    if wants_json:
        return jsonify(
            ok=True,
            message=message,
            client_id=client.id if client else None,
            price_list=price_list_name,
            cart=cart,
        )
    flash(message, 'success' if client else 'info')
    return redirect(create_url)


@sales_bp.route('/remove-item/<int:item_id>', methods=['POST'])
def remove_item(item_id):
    company_id = session.get('company_id')
    sale_id = session.get('current_sale_id')
    wants_json = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or 'application/json' in request.headers.get('Accept', '')
    )

    def reject(message, status=400, redirect_url=None):
        destination = redirect_url or url_for('sales_bp.create_sale')
        if wants_json:
            return jsonify(
                ok=False,
                error=message,
                redirect=destination,
                request_id=getattr(g, 'request_id', None),
            ), status
        flash(message, 'danger' if status >= 400 else 'warning')
        return redirect(destination)

    if not company_id or not session.get('user_id'):
        return reject(
            'Tu sesión expiró. Inicia sesión nuevamente para continuar.',
            401,
            url_for('login_bp.login'),
        )
    if not sale_id:
        return reject('No hay una venta activa para modificar.', 409)

    sale = editable_sales_query(company_id, session.get('user_id')).filter_by(id=sale_id).with_for_update().first()
    if not sale:
        session.pop('current_sale_id', None)
        return reject('La venta activa ya no existe. Recarga la caja para iniciar un pedido nuevo.', 404)
    if sale.status not in {'DRAFT', 'PENDING', 'QUOTATION'}:
        return reject(
            'Esta venta ya no admite modificaciones.',
            409,
            url_for('sales_bp.list_sales'),
        )
    item = SaleItem.query.filter_by(id=item_id, sale_id=sale.id).first()
    if not item:
        return reject('La línea ya no existe en este pedido.', 404)

    try:
        release_serials_for_item(item)
        # Removing the object from the relationship updates the in-memory cart
        # before totals are recalculated. Calling ``session.delete`` alone leaves
        # the deleted row in ``sale.items`` until expiration and can preserve its
        # amount in the order total for the remainder of this request.
        sale.items.remove(item)
        recalc_sale(sale)
        cart = _sale_cart_payload(sale)
        db.session.commit()
    except (BusinessRuleError, NumericValueError) as exc:
        db.session.rollback()
        return reject(str(exc), 400)
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            'Unexpected POS remove failure request_id=%s company_id=%s sale_id=%s item_id=%s',
            getattr(g, 'request_id', None), company_id, sale_id, item_id,
        )
        return reject(
            'No se pudo quitar el producto por un error interno. El pedido no fue modificado; '
            'recárgalo y vuelve a intentarlo. Si continúa, comparte la referencia mostrada.',
            500,
        )

    if wants_json:
        return jsonify(
            ok=True,
            message='Producto eliminado del pedido.',
            cart=cart,
        )
    flash('Producto eliminado', 'info')
    return redirect(url_for('sales_bp.create_sale'))


def _catalog_stock_snapshot(company_id, warehouse_id, products, variants, *, sale_id=None):
    """Return available stock maps for one POS warehouse without N+1 queries.

    Active reservations from other sales and pending outbound transfers are
    subtracted. Reservations owned by the current cart remain available to that
    same cart, matching the final stock validator used when adding a line.
    """
    if not warehouse_id or not products:
        return {}, {}

    product_ids = [int(product.id) for product in products]
    variant_ids = [int(variant.id) for variant in variants]
    product_stock = {
        int(product_id): as_decimal(quantity)
        for product_id, quantity in db.session.query(
            WarehouseStock.product_id, WarehouseStock.quantity,
        ).filter(
            WarehouseStock.company_id == company_id,
            WarehouseStock.warehouse_id == warehouse_id,
            WarehouseStock.product_id.in_(product_ids),
        ).all()
    }
    variant_stock = {
        int(variant_id): as_decimal(quantity)
        for variant_id, quantity in db.session.query(
            WarehouseVariantStock.variant_id, WarehouseVariantStock.quantity,
        ).filter(
            WarehouseVariantStock.company_id == company_id,
            WarehouseVariantStock.warehouse_id == warehouse_id,
            WarehouseVariantStock.variant_id.in_(variant_ids),
        ).all()
    } if variant_ids else {}

    transfer_rows = db.session.query(
        StockTransfer.product_id,
        func.coalesce(func.sum(StockTransfer.quantity), 0),
    ).filter(
        StockTransfer.company_id == company_id,
        StockTransfer.from_warehouse_id == warehouse_id,
        StockTransfer.status == 'PENDING',
        StockTransfer.product_id.in_(product_ids),
    ).group_by(StockTransfer.product_id).all()
    transfer_reserved = {int(product_id): as_decimal(quantity) for product_id, quantity in transfer_rows}

    reservation_query = db.session.query(
        StockReservation.product_id,
        StockReservation.variant_id,
        func.coalesce(func.sum(StockReservation.quantity), 0),
    ).join(SaleItem, StockReservation.sale_item_id == SaleItem.id).filter(
        StockReservation.company_id == company_id,
        StockReservation.warehouse_id == warehouse_id,
        StockReservation.status == 'ACTIVE',
        StockReservation.product_id.in_(product_ids),
    )
    if sale_id:
        reservation_query = reservation_query.filter(SaleItem.sale_id != sale_id)
    reservation_rows = reservation_query.group_by(
        StockReservation.product_id, StockReservation.variant_id,
    ).all()
    sale_reserved = {
        (int(product_id), int(variant_id) if variant_id is not None else None): as_decimal(quantity)
        for product_id, variant_id, quantity in reservation_rows
    }

    available_products = {}
    for product_id in product_ids:
        available_products[product_id] = max(
            product_stock.get(product_id, finite_decimal('0'))
            - transfer_reserved.get(product_id, finite_decimal('0'))
            - sale_reserved.get((product_id, None), finite_decimal('0')),
            finite_decimal('0'),
        )

    available_variants = {}
    variant_product = {int(variant.id): int(variant.product_id) for variant in variants}
    for variant_id in variant_ids:
        product_id = variant_product[variant_id]
        available_variants[variant_id] = max(
            variant_stock.get(variant_id, finite_decimal('0'))
            - transfer_reserved.get(product_id, finite_decimal('0'))
            - sale_reserved.get((product_id, variant_id), finite_decimal('0')),
            finite_decimal('0'),
        )
    return available_products, available_variants


def _catalog_stock_state(product, variant, warehouse, product_stock, variant_stock):
    if product.product_type == ProductType.SERVICE:
        return {
            'stock_quantity': None,
            'stock_state': 'service',
            'stock_label': 'Servicio · sin inventario',
            'stock_error': '',
            'stock_warning': '',
        }
    if warehouse is None:
        return {
            'stock_quantity': None,
            'stock_state': 'unknown',
            'stock_label': 'Selecciona almacén',
            'stock_error': '',
            'stock_warning': 'Selecciona un almacén para consultar disponibilidad real.',
        }

    quantity = (
        variant_stock.get(int(variant.id), finite_decimal('0'))
        if variant is not None
        else product_stock.get(int(product.id), finite_decimal('0'))
    )
    symbol = getattr(product.base_uom, 'symbol', None) or 'ud'
    visible = display_quantity(quantity)
    location = warehouse.name
    if quantity <= 0:
        return {
            'stock_quantity': str(quantity),
            'stock_state': 'out',
            'stock_label': f'Sin stock · {location}',
            'stock_error': f'No hay stock disponible en {location}.',
            'stock_warning': '',
        }
    minimum = as_decimal(product.min_stock or 0)
    if minimum > 0 and quantity <= minimum:
        return {
            'stock_quantity': str(quantity),
            'stock_state': 'low',
            'stock_label': f'{visible} {symbol} disponibles',
            'stock_error': '',
            'stock_warning': f'Stock bajo en {location}: quedan {visible} {symbol}.',
        }
    return {
        'stock_quantity': str(quantity),
        'stock_state': 'ok',
        'stock_label': f'{visible} {symbol} disponibles',
        'stock_error': '',
        'stock_warning': '',
    }


@sales_bp.route('/get_products')
def get_products():
    company_id = session.get('company_id')
    if not company_id:
        return jsonify([]), 401

    search_query = request.args.get('search', '').strip()[:120]
    sale = Sale.query.filter_by(
        id=session.get('current_sale_id'), company_id=company_id, user_id=session.get('user_id'),
    ).first()
    client = sale.client if sale else None
    user = User.query.filter_by(id=session.get('user_id'), company_id=company_id).first()
    if not user:
        return jsonify(error='Tu sesión ya no corresponde a un usuario activo.'), 401

    requested_terminal_id = session.get('sales_terminal_id') if not user.terminal_id else user.terminal_id
    requested_warehouse_id = request.args.get('warehouse_id', type=int)
    if requested_warehouse_id is None and not user.warehouse_id:
        requested_warehouse_id = session.get('sales_warehouse_id')
    try:
        sale_terminal = resolve_sale_terminal(
            user, company_id, requested_id=requested_terminal_id, sale=sale,
        )
        sale_warehouse = resolve_sale_warehouse(
            user, company_id, requested_id=requested_warehouse_id,
            sale=sale, terminal=sale_terminal,
        )
    except (BusinessRuleError, NumericValueError, TypeError, ValueError) as exc:
        return jsonify(error=str(exc)), 400

    query = Product.query.filter_by(company_id=company_id, status=True).filter(Product.archived_at.is_(None))
    matched_variant_ids = []
    matched_product_ids = []
    if search_query:
        like = f'%{search_query}%'
        matched_product_ids = [row[0] for row in db.session.query(ProductBarcode.product_id).filter(
            ProductBarcode.company_id == company_id, ProductBarcode.code.ilike(like)
        ).limit(100).all()]
        matched_variant_ids = [row[0] for row in db.session.query(ProductVariant.id).filter(
            ProductVariant.company_id == company_id,
            or_(ProductVariant.sku.ilike(like), ProductVariant.name.ilike(like)),
            ProductVariant.active.is_(True),
        ).limit(100).all()]
        variant_product_ids = (
            [row[0] for row in db.session.query(ProductVariant.product_id).filter(
                ProductVariant.id.in_(matched_variant_ids)
            ).all()]
            if matched_variant_ids else []
        )
        ids = set(matched_product_ids + variant_product_ids)
        query = query.filter(or_(
            Product.name.ilike(like),
            Product.sku.ilike(like),
            Product.id.in_(ids) if ids else False,
        ))

    products = query.order_by(Product.name.asc()).limit(60).all()
    product_ids = [int(product.id) for product in products]
    all_variants = (
        ProductVariant.query.filter(
            ProductVariant.company_id == company_id,
            ProductVariant.product_id.in_(product_ids),
            ProductVariant.active.is_(True),
        ).order_by(ProductVariant.product_id.asc(), ProductVariant.name.asc()).all()
        if product_ids else []
    )
    variants_by_product = {}
    for variant in all_variants:
        variants_by_product.setdefault(int(variant.product_id), []).append(variant)
    product_stock, variant_stock = _catalog_stock_snapshot(
        company_id, sale_warehouse.id if sale_warehouse else None,
        products, all_variants, sale_id=sale.id if sale else None,
    )

    results = []
    for product in products:
        product_type = str(
            product.product_type.value
            if hasattr(product.product_type, 'value')
            else product.product_type
        ).upper()

        product_warnings = []
        product_errors = []
        try:
            uom_options = _compatible_uoms(product)
        except (BusinessRuleError, NumericValueError) as exc:
            current_app.logger.warning(
                'POS catalog skipped invalid UOM configuration for product_id=%s: %s',
                product.id, exc,
            )
            base_uom = product.base_uom
            if base_uom and base_uom.active:
                uom_options = [(base_uom, finite_decimal('1'))]
                product_warnings.append('Se ocultaron unidades de medida con una conversión inválida.')
            else:
                uom_options = []
                product_errors.append('Revisa las unidades de medida de este producto.')

        variants = variants_by_product.get(int(product.id), [])
        candidates = variants if variants else [None]
        if search_query and matched_variant_ids and variants:
            narrowed = [variant for variant in variants if variant.id in matched_variant_ids]
            product_matches = (
                search_query.lower() in (product.name or '').lower()
                or search_query.lower() in (product.sku or '').lower()
            )
            if narrowed and not product_matches:
                candidates = narrowed

        for variant in candidates[:40]:
            row_errors = list(product_errors)
            row_warnings = list(product_warnings)
            stock_state = _catalog_stock_state(
                product, variant, sale_warehouse, product_stock, variant_stock,
            )
            if stock_state['stock_error']:
                row_errors.append(stock_state['stock_error'])
            if stock_state['stock_warning']:
                row_warnings.append(stock_state['stock_warning'])
            try:
                price, price_list = resolve_sale_price(
                    product,
                    quantity=finite_decimal('1'),
                    company_id=company_id,
                    client=client,
                    variant=variant,
                    price_list_id=sale.price_list_id if sale else None,
                )
            except (BusinessRuleError, NumericValueError) as exc:
                current_app.logger.warning(
                    'POS catalog found invalid pricing for product_id=%s variant_id=%s: %s',
                    product.id, variant.id if variant else None, exc,
                )
                price_list = None
                try:
                    price = _catalog_fallback_price(product, variant)
                except (BusinessRuleError, NumericValueError):
                    price = finite_decimal('0')
                row_errors.append('Revisa la configuración de precio antes de vender este producto.')

            image_path = variant.image_path if variant and variant.image_path else None
            image_url = url_for('static', filename=image_path) if image_path else None
            if not image_url:
                image_url = product_image_url(product)

            # Preserve order while removing duplicate warnings/errors.
            row_errors = list(dict.fromkeys(row_errors))
            row_warnings = list(dict.fromkeys(row_warnings))
            results.append({
                'id': product.id,
                'variant_id': variant.id if variant else None,
                'name': variant.name if variant else product.name,
                'base_name': product.name,
                'price': float(price),
                'sku': variant.sku if variant else product.sku,
                'category': product.category.name if product.category else 'General',
                'type': product_type,
                'sale_mode': product.sale_mode,
                'tracking': product.tracking,
                'image': image_url,
                'default_uom_id': product.sale_uom_id or product.base_uom_id,
                'uoms': [
                    {
                        'id': unit.id,
                        'name': unit.name,
                        'symbol': unit.symbol,
                        'factor': float(factor),
                        'allow_fraction': bool(unit.allow_fraction),
                    }
                    for unit, factor in uom_options
                ],
                'price_list': price_list.name if price_list else 'Precio público',
                'warehouse_name': sale_warehouse.name if sale_warehouse else None,
                'stock_quantity': stock_state['stock_quantity'],
                'stock_state': stock_state['stock_state'],
                'stock_label': stock_state['stock_label'],
                'available': not row_errors,
                'unavailable_reason': ' '.join(row_errors),
                'catalog_warning': ' '.join(row_warnings),
            })
            if len(results) >= 80:
                break
        if len(results) >= 80:
            break

    response = jsonify(results)
    response.headers['Cache-Control'] = 'private, no-store, max-age=0'
    return response
