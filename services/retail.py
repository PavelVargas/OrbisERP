"""Retail-domain services shared by POS, catalog and integrations."""
from __future__ import annotations

from services.numeric import NumericValueError, bounded_decimal, finite_decimal
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import or_, func

from db import db
from services.time_utils import utcnow
from services.quantity import as_decimal, base_quantity_from_factor
from services.validation import BusinessRuleError
from models.retail import (
    CompanyRetailSettings,
    PriceList,
    PriceListRule,
    UnitOfMeasure, ProductUomConversion,
    WarehouseVariantStock,
    InventoryLot,
    InventorySerial,
    InventorySerialEvent,
    StockReservation,
    SaleItemLotAllocation,
    LoyaltyTransaction,
)
from models.stock_transfer.stock_transfer import StockTransfer
from models.warehouse_stock.warehouse_stock import WarehouseStock


def get_retail_settings(company_id, *, create=False):
    settings = db.session.get(CompanyRetailSettings, company_id)
    if settings or not create:
        return settings
    settings = CompanyRetailSettings(company_id=company_id)
    db.session.add(settings)
    db.session.flush()
    return settings


def get_default_price_list(company_id):
    return PriceList.query.filter_by(company_id=company_id, active=True, is_default=True).first()


def resolve_price_list(company_id, client=None, explicit_id=None):
    if explicit_id:
        row = PriceList.query.filter_by(id=explicit_id, company_id=company_id, active=True).first()
        if row:
            return row
    if client and getattr(client, 'price_list_id', None):
        row = PriceList.query.filter_by(id=client.price_list_id, company_id=company_id, active=True).first()
        if row:
            return row
    return get_default_price_list(company_id)


def _rule_specificity(rule, product, variant):
    if variant and rule.variant_id == variant.id:
        return 4
    if rule.product_id == product.id and not rule.variant_id:
        return 3
    if rule.category_id and rule.category_id == product.category_id:
        return 2
    if not rule.variant_id and not rule.product_id and not rule.category_id:
        return 1
    return 0


def _bounded_price_percent(value, *, field_name='Porcentaje'):
    """Validate price-rule percentages, including historical database rows."""
    parsed = finite_decimal(value, field_name=field_name)
    if parsed < 0 or parsed > 100:
        raise BusinessRuleError(f'{field_name} debe estar entre 0 y 100.')
    return parsed


def resolve_sale_price(product, *, quantity=finite_decimal('1'), company_id=None, client=None, variant=None, price_list_id=None):
    if product is None:
        raise BusinessRuleError(
            'No se pudo determinar el producto para calcular el precio de venta. Recarga la caja y vuelve a intentarlo.'
        )
    company_id = company_id or product.company_id
    if int(product.company_id) != int(company_id):
        raise BusinessRuleError('El producto no pertenece a la empresa usada para calcular el precio.')
    if not bool(getattr(product, 'status', False)) or getattr(product, 'archived_at', None) is not None:
        raise BusinessRuleError('El producto está desactivado o archivado y no admite cálculo de precio de venta.')
    if variant is not None and (
        int(variant.product_id) != int(product.id)
        or int(variant.company_id) != int(company_id)
        or not variant.active
    ):
        raise BusinessRuleError('La variante no es válida para calcular el precio de este producto.')
    qty = as_decimal(quantity)
    if qty <= 0:
        raise BusinessRuleError('La cantidad para calcular el precio debe ser mayor que cero.')
    base = as_decimal(product.price) + (as_decimal(variant.price_extra) if variant else finite_decimal('0'))
    if base < 0:
        raise BusinessRuleError('El precio de venta resultante no puede ser negativo.')
    price_list = resolve_price_list(company_id, client=client, explicit_id=price_list_id)
    if not price_list:
        return base.quantize(finite_decimal('0.01')), None

    now = utcnow()
    candidates = PriceListRule.query.filter(
        PriceListRule.company_id == company_id,
        PriceListRule.price_list_id == price_list.id,
        PriceListRule.active.is_(True),
        PriceListRule.min_quantity <= qty,
        or_(PriceListRule.starts_at.is_(None), PriceListRule.starts_at <= now),
        or_(PriceListRule.ends_at.is_(None), PriceListRule.ends_at >= now),
    ).all()
    applicable = [r for r in candidates if _rule_specificity(r, product, variant)]
    if not applicable:
        return base.quantize(finite_decimal('0.01')), price_list
    applicable.sort(key=lambda r: (_rule_specificity(r, product, variant), as_decimal(r.min_quantity), -int(r.priority or 10)), reverse=True)
    rule = applicable[0]
    if rule.rule_type == 'FIXED' and rule.fixed_price is not None:
        price = as_decimal(rule.fixed_price)
    elif rule.rule_type == 'DISCOUNT':
        percent = _bounded_price_percent(rule.percent, field_name='Porcentaje de descuento')
        price = base * (finite_decimal('1') - percent / finite_decimal('100'))
    elif rule.rule_type == 'SURCHARGE':
        percent = _bounded_price_percent(rule.percent, field_name='Porcentaje de recargo')
        price = base * (finite_decimal('1') + percent / finite_decimal('100'))
    else:
        price = base
    return max(price, finite_decimal('0')).quantize(finite_decimal('0.01')), price_list


def uom_factor_to_base(product, uom_id=None, *, purpose=None):
    """Return how many base units one selected UOM represents for this product.

    Product-specific conversions take precedence over the generic UOM factor. This
    is essential for retail because a "Caja" can mean 6 units for one product and
    24 for another. Generic factors remain as a compatibility fallback for physical
    units such as kg/g or m/cm.
    """
    if not uom_id:
        return finite_decimal('1')
    selected = UnitOfMeasure.query.filter_by(id=uom_id, company_id=product.company_id, active=True).first()
    if not selected:
        raise BusinessRuleError('La unidad de medida seleccionada no está disponible.')
    base = product.base_uom or selected
    if base and selected.category != base.category:
        raise BusinessRuleError('La unidad seleccionada no pertenece a la misma categoría de medida del producto.')
    if base and selected.id == base.id:
        return finite_decimal('1')
    conversion = ProductUomConversion.query.filter_by(
        company_id=product.company_id, product_id=product.id, uom_id=selected.id
    ).first()
    if conversion:
        if purpose == 'sale' and not conversion.allow_sale:
            raise BusinessRuleError(f'{selected.name} no está habilitada como unidad de venta para este producto.')
        if purpose == 'purchase' and not conversion.allow_purchase:
            raise BusinessRuleError(f'{selected.name} no está habilitada como unidad de compra para este producto.')
        factor = as_decimal(conversion.factor_to_base)
        if factor <= 0:
            raise BusinessRuleError('La conversión configurada no tiene un factor positivo válido.')
        return factor
    # Backward-compatible fallback. Product-specific packaging should always use
    # ProductUomConversion instead of changing a company-wide unit factor.
    selected_factor = as_decimal(selected.factor_to_reference)
    base_factor = as_decimal(base.factor_to_reference)
    if selected_factor <= 0 or base_factor <= 0:
        raise BusinessRuleError('La unidad de medida tiene un factor de referencia inválido.')
    return (selected_factor / base_factor).quantize(finite_decimal('0.000001'), rounding=ROUND_HALF_UP)


def uom_to_base(product, quantity, uom_id=None, *, purpose=None):
    qty = as_decimal(quantity)
    if not uom_id:
        return qty
    selected = UnitOfMeasure.query.filter_by(id=uom_id, company_id=product.company_id, active=True).first()
    if not selected:
        raise BusinessRuleError('La unidad de medida seleccionada no está disponible.')
    if not selected.allow_fraction and qty != qty.to_integral_value():
        raise BusinessRuleError(f'{selected.name} no admite cantidades fraccionarias.')
    factor = uom_factor_to_base(product, selected.id, purpose=purpose)
    try:
        return base_quantity_from_factor(qty, factor, 'Cantidad base', allow_zero=True)
    except NumericValueError as exc:
        raise BusinessRuleError(
            'La conversión produce una cantidad que el inventario no puede representar con 3 decimales.'
        ) from exc


def product_uom_options(product, *, purpose='sale'):
    """Return UOMs actually enabled for this product and their product factor."""
    base = product.base_uom
    if not base:
        return []
    conversions = ProductUomConversion.query.filter_by(
        company_id=product.company_id, product_id=product.id
    ).all()
    allowed = {base.id: (base, finite_decimal('1'))}
    for row in conversions:
        if purpose == 'sale' and not row.allow_sale:
            continue
        if purpose == 'purchase' and not row.allow_purchase:
            continue
        if row.uom and row.uom.active and row.uom.category == base.category:
            allowed[row.uom.id] = (row.uom, as_decimal(row.factor_to_base))
    preferred_id = product.sale_uom_id if purpose == 'sale' else product.purchase_uom_id if purpose == 'purchase' else None
    if preferred_id and preferred_id not in allowed:
        unit = UnitOfMeasure.query.filter_by(id=preferred_id, company_id=product.company_id, active=True).first()
        if unit and unit.category == base.category:
            allowed[unit.id] = (unit, uom_factor_to_base(product, unit.id))
    # Existing installations may not yet have product-specific mappings. Expose
    # only units with a meaningful company-wide physical factor (kg/g, m/cm,
    # etc.). Ambiguous packaging with the same factor as the base unit (Caja,
    # Paquete...) must be configured explicitly per product.
    if not conversions:
        base_factor = as_decimal(base.factor_to_reference or 1)
        for unit in UnitOfMeasure.query.filter_by(company_id=product.company_id, category=base.category, active=True).all():
            unit_factor = as_decimal(unit.factor_to_reference or 1)
            if unit.id == base.id or unit_factor != base_factor:
                allowed[unit.id] = (unit, uom_factor_to_base(product, unit.id))
    rows = list(allowed.values())
    rows.sort(key=lambda pair: (pair[1], pair[0].name.lower()))
    return rows


def available_sale_stock(product_id, warehouse_id, company_id, *, variant_id=None):
    if variant_id:
        stock = WarehouseVariantStock.query.filter_by(
            product_id=product_id, variant_id=variant_id, warehouse_id=warehouse_id, company_id=company_id
        ).first()
    else:
        stock = WarehouseStock.query.filter_by(product_id=product_id, warehouse_id=warehouse_id, company_id=company_id).first()
    if not stock:
        return finite_decimal('0')
    reserved_transfer = db.session.query(func.coalesce(func.sum(StockTransfer.quantity), 0)).filter(
        StockTransfer.product_id == product_id,
        StockTransfer.from_warehouse_id == warehouse_id,
        StockTransfer.company_id == company_id,
        StockTransfer.status == 'PENDING',
    ).scalar()
    reserved_sale = db.session.query(func.coalesce(func.sum(StockReservation.quantity), 0)).filter(
        StockReservation.product_id == product_id,
        StockReservation.warehouse_id == warehouse_id,
        StockReservation.company_id == company_id,
        StockReservation.status == 'ACTIVE',
    )
    if variant_id:
        reserved_sale = reserved_sale.filter(StockReservation.variant_id == variant_id)
    else:
        reserved_sale = reserved_sale.filter(StockReservation.variant_id.is_(None))
    reserved_sale = reserved_sale.scalar()
    return max(as_decimal(stock.quantity) - as_decimal(reserved_transfer) - as_decimal(reserved_sale), finite_decimal('0'))


def allocate_fefo(item, *, commit=False):
    """Allocate LOT tracked inventory to a completed sale item using FEFO."""
    product = item.product
    if getattr(product, 'tracking', 'NONE') != 'LOT':
        return []
    needed = as_decimal(item.quantity) * as_decimal(item.uom_factor or 1)
    rows = InventoryLot.query.filter(
        InventoryLot.company_id == item.sale.company_id,
        InventoryLot.product_id == item.product_id,
        InventoryLot.warehouse_id == item.warehouse_id,
        InventoryLot.status == 'AVAILABLE',
        InventoryLot.quantity > 0,
        or_(InventoryLot.expires_at.is_(None), InventoryLot.expires_at >= date.today()),
    )
    if item.variant_id:
        rows = rows.filter(InventoryLot.variant_id == item.variant_id)
    else:
        rows = rows.filter(InventoryLot.variant_id.is_(None))
    rows = rows.order_by(InventoryLot.expires_at.asc().nullslast(), InventoryLot.received_at.asc(), InventoryLot.id.asc()).with_for_update().all()
    total = sum((as_decimal(r.quantity) for r in rows), finite_decimal('0'))
    if total < needed:
        raise BusinessRuleError(f'Lotes insuficientes para {product.name}; disponible {total}, requerido {needed}.')
    allocations = []
    remaining = needed
    for lot in rows:
        if remaining <= 0:
            break
        used = min(as_decimal(lot.quantity), remaining)
        lot.quantity = as_decimal(lot.quantity) - used
        if lot.quantity <= 0:
            lot.quantity = finite_decimal('0')
            lot.status = 'DEPLETED'
        allocation = SaleItemLotAllocation(
            company_id=item.sale.company_id,
            sale_item_id=item.id,
            lot_id=lot.id,
            quantity=used,
        )
        db.session.add(allocation)
        allocations.append(allocation)
        remaining -= used
    if commit:
        db.session.commit()
    return allocations


def reserve_serials_for_item(item):
    product = item.product
    if getattr(product, 'tracking', 'NONE') != 'SERIAL':
        return []
    needed = int(as_decimal(item.quantity) * as_decimal(item.uom_factor or 1))
    if as_decimal(item.quantity) * as_decimal(item.uom_factor or 1) != needed:
        raise BusinessRuleError('Los productos serializados solo admiten cantidades enteras.')
    existing = InventorySerial.query.filter_by(
        company_id=item.sale.company_id,
        sale_item_id=item.id,
        status='RESERVED',
    ).order_by(InventorySerial.id.asc()).all()
    if len(existing) > needed:
        for serial in existing[needed:]:
            serial.status = 'AVAILABLE'
            serial.sale_item_id = None
        existing = existing[:needed]
    missing = needed - len(existing)
    if missing > 0:
        query = InventorySerial.query.filter_by(
            company_id=item.sale.company_id,
            product_id=item.product_id,
            warehouse_id=item.warehouse_id,
            status='AVAILABLE',
        )
        if item.variant_id:
            query = query.filter_by(variant_id=item.variant_id)
        else:
            query = query.filter(InventorySerial.variant_id.is_(None))
        rows = query.order_by(InventorySerial.acquired_at.asc(), InventorySerial.id.asc()).with_for_update().limit(missing).all()
        if len(rows) < missing:
            raise BusinessRuleError(f'No hay suficientes números de serie disponibles para {product.name}.')
        for serial in rows:
            serial.status = 'RESERVED'
            serial.sale_item_id = item.id
        existing.extend(rows)
    return existing


def release_serials_for_item(item):
    for serial in InventorySerial.query.filter_by(company_id=item.sale.company_id, sale_item_id=item.id, status='RESERVED').all():
        serial.status = 'AVAILABLE'
        serial.sale_item_id = None


def complete_serials_for_item(item):
    warranty_days = int(getattr(item.product, 'warranty_days', 0) or 0)
    sold_date = utcnow()
    from datetime import timedelta
    rows = InventorySerial.query.filter_by(company_id=item.sale.company_id, sale_item_id=item.id, status='RESERVED').with_for_update().all()
    expected = int(as_decimal(item.quantity) * as_decimal(item.uom_factor or 1))
    if getattr(item.product, 'tracking', 'NONE') == 'SERIAL' and len(rows) != expected:
        raise BusinessRuleError(f'Faltan seriales reservados para {item.product.name}.')
    for serial in rows:
        serial.status = 'SOLD'
        serial.sold_at = sold_date
        serial.warranty_until = (sold_date + timedelta(days=warranty_days)).date() if warranty_days else None
        db.session.add(InventorySerialEvent(
            company_id=item.sale.company_id,
            serial_id=serial.id,
            event_type='SOLD',
            sale_item_id=item.id,
            warehouse_id=item.warehouse_id,
            notes=f'Venta #{item.sale_id}',
        ))
    return rows


def ensure_credit_allowed(client, sale_total):
    if not client:
        raise BusinessRuleError('Selecciona un cliente para vender a crédito.')
    if not getattr(client, 'credit_enabled', False) or getattr(client, 'credit_hold', False):
        raise BusinessRuleError('El cliente no tiene crédito habilitado o se encuentra bloqueado.')
    from models.sales.sales import Sale
    used = db.session.query(func.coalesce(func.sum(Sale.balance), 0)).filter(
        Sale.company_id == client.company_id,
        Sale.client_id == client.id,
        Sale.status == 'COMPLETED',
        Sale.balance > 0,
    ).scalar()
    available = max(as_decimal(client.credit_limit) - as_decimal(used), finite_decimal('0'))
    if as_decimal(sale_total) > available:
        raise BusinessRuleError(f'Crédito insuficiente. Disponible: {available:.2f}.')
    return available


def accrue_loyalty(client, sale, settings):
    if not client or not settings or not settings.enable_loyalty:
        return None
    rate = as_decimal(settings.loyalty_points_per_currency)
    if rate <= 0:
        return None
    points = (as_decimal(sale.total) * rate).quantize(finite_decimal('0.0001'), rounding=ROUND_HALF_UP)
    if points <= 0:
        return None
    client.loyalty_points = as_decimal(client.loyalty_points) + points
    tx = LoyaltyTransaction(
        company_id=sale.company_id,
        client_id=client.id,
        sale_id=sale.id,
        event_type='EARN',
        points=points,
        balance_after=client.loyalty_points,
        notes=f'Venta #{sale.id}',
    )
    db.session.add(tx)
    return tx


def loyalty_redemption_quote(client, points, settings, *, max_amount=None):
    """Validate a loyalty redemption and return ``(points, monetary_amount)``.

    Points are intentionally represented with Decimal because some programs
    award fractional points.  The monetary amount is rounded to cents and may
    not exceed ``max_amount`` when supplied.
    """
    if not client:
        raise BusinessRuleError('Selecciona un cliente para usar puntos de fidelidad.')
    if not settings or not settings.enable_loyalty:
        raise BusinessRuleError('El programa de fidelidad no está habilitado para esta empresa.')
    requested = bounded_decimal(
        points or 0, field_name='Puntos a redimir', places=4,
        minimum='0', maximum='9999999999.9999',
    )
    if requested <= 0:
        return finite_decimal('0.0000'), finite_decimal('0.00')
    available = as_decimal(client.loyalty_points or 0).quantize(finite_decimal('0.0001'), rounding=ROUND_HALF_UP)
    if requested > available:
        raise BusinessRuleError(f'Puntos insuficientes. Disponible: {available:.4f}.')
    value_per_point = as_decimal(settings.loyalty_currency_per_point or 0)
    if value_per_point <= 0:
        raise BusinessRuleError('Configura el valor monetario por punto antes de permitir redenciones.')
    amount = (requested * value_per_point).quantize(finite_decimal('0.01'))
    if amount <= 0:
        raise BusinessRuleError('La redención seleccionada no genera un valor monetario utilizable.')
    if max_amount is not None and amount > as_decimal(max_amount).quantize(finite_decimal('0.01')):
        raise BusinessRuleError('El valor de los puntos no puede superar el total de la venta.')
    return requested, amount


def redeem_loyalty(client, sale, points, settings):
    """Persist a loyalty redemption inside the caller's transaction."""
    requested, amount = loyalty_redemption_quote(client, points, settings, max_amount=sale.total)
    if requested <= 0:
        return None, finite_decimal('0.00')
    # Lock the customer balance before mutating it.  This protects simultaneous
    # POS sessions from spending the same points twice.
    locked = client.__class__.query.filter_by(id=client.id, company_id=client.company_id).with_for_update().first()
    if not locked:
        raise BusinessRuleError('No se pudo validar la cuenta de fidelidad del cliente.')
    requested, amount = loyalty_redemption_quote(locked, requested, settings, max_amount=sale.total)
    locked.loyalty_points = as_decimal(locked.loyalty_points) - requested
    tx = LoyaltyTransaction(
        company_id=sale.company_id,
        client_id=locked.id,
        sale_id=sale.id,
        event_type='REDEEM',
        points=-requested,
        balance_after=locked.loyalty_points,
        notes=f'Redención en venta #{sale.id} por {amount:.2f}',
    )
    db.session.add(tx)
    return tx, amount


