"""Transactional retail sale engine.

Keeps stock, variants, locations, lots/serials, reservations and loyalty in one
place so POS, layaway completion and future API sales share the same rules.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func

from db import db
from models.products.products import ProductType
from models.retail import (
    WarehouseVariantStock, StockReservation, ProductBundleItem,
)
from models.stock_movement.stock_movement import StockMovement
from models.stock_transfer.stock_transfer import StockTransfer
from models.warehouse_stock.warehouse_stock import WarehouseStock
from models.warehouse_location.warehouse_location import LocationStock, WarehouseLocation
from models.sales.sale_item import SaleItem
from services.quantity import as_decimal, base_quantity_from_factor, display_quantity
from services.validation import BusinessRuleError
from services.retail import allocate_fefo, complete_serials_for_item, accrue_loyalty
from services.costing import sale_line_unit_cost
from services.time_utils import utcnow


def base_quantity(item):
    return base_quantity_from_factor(item.quantity, item.uom_factor or 1, 'Cantidad base de venta')


def is_service(product):
    return product.product_type == ProductType.SERVICE


def stock_requirements(item):
    """Return inventory requirements for a sale item.

    A normal item consumes itself. A kit/combination is virtual and consumes its
    component products instead, preventing duplicated stock for the commercial
    bundle and its physical parts.
    """
    if is_service(item.product):
        return []
    line_qty = base_quantity(item)
    bundle_rows = ProductBundleItem.query.filter_by(
        company_id=item.sale.company_id,
        bundle_product_id=item.product_id,
    ).all()
    if not bundle_rows:
        return [(item.product_id, item.variant_id, line_qty, item.product.name)]
    requirements = []
    for row in bundle_rows:
        if is_service(row.component):
            continue
        requirements.append((
            row.component_product_id,
            row.component_variant_id,
            base_quantity_from_factor(line_qty, row.quantity, 'Cantidad de componente'),
            row.component.name,
        ))
    return requirements


def _other_reservations(company_id, product_id, warehouse_id, *, variant_id=None, sale_id=None):
    query = db.session.query(func.coalesce(func.sum(StockReservation.quantity), 0)).join(
        SaleItem, StockReservation.sale_item_id == SaleItem.id
    ).filter(
        StockReservation.company_id == company_id,
        StockReservation.product_id == product_id,
        StockReservation.warehouse_id == warehouse_id,
        StockReservation.status == 'ACTIVE',
    )
    if variant_id:
        query = query.filter(StockReservation.variant_id == variant_id)
    else:
        query = query.filter(StockReservation.variant_id.is_(None))
    if sale_id:
        query = query.filter(SaleItem.sale_id != sale_id)
    return as_decimal(query.scalar())


def available_requirement(company_id, product_id, warehouse_id, *, variant_id=None, sale_id=None):
    if variant_id:
        row = WarehouseVariantStock.query.filter_by(
            company_id=company_id, product_id=product_id,
            warehouse_id=warehouse_id, variant_id=variant_id,
        ).first()
    else:
        row = WarehouseStock.query.filter_by(
            company_id=company_id, product_id=product_id, warehouse_id=warehouse_id,
        ).first()
    if not row:
        return Decimal('0')
    transfers = db.session.query(func.coalesce(func.sum(StockTransfer.quantity), 0)).filter(
        StockTransfer.company_id == company_id,
        StockTransfer.product_id == product_id,
        StockTransfer.from_warehouse_id == warehouse_id,
        StockTransfer.status == 'PENDING',
    ).scalar()
    return max(
        as_decimal(row.quantity) - as_decimal(transfers)
        - _other_reservations(company_id, product_id, warehouse_id, variant_id=variant_id, sale_id=sale_id),
        Decimal('0'),
    )


def ensure_item_available(item, warehouse_id=None, *, sale_id=None):
    wid = warehouse_id or item.warehouse_id
    if not wid:
        raise BusinessRuleError(f'{item.product.name} no tiene almacén de origen.')
    for product_id, variant_id, qty, label in stock_requirements(item):
        available = available_requirement(
            item.sale.company_id, product_id, wid,
            variant_id=variant_id, sale_id=sale_id,
        )
        if available < qty:
            raise BusinessRuleError(f'Stock insuficiente para {label}. Disponible {display_quantity(available)}, requerido {display_quantity(qty)}.')
    return True


def _deduct_location_stock(company_id, product_id, warehouse_id, required_qty):
    """Reduce assigned location stock without forcing all stock to have a location."""
    stock = WarehouseStock.query.filter_by(
        company_id=company_id, product_id=product_id, warehouse_id=warehouse_id
    ).with_for_update().first()
    if not stock or as_decimal(stock.quantity) < required_qty:
        raise BusinessRuleError('El stock físico no coincide con la disponibilidad calculada.')

    location_rows = LocationStock.query.join(WarehouseLocation).filter(
        WarehouseLocation.company_id == company_id,
        WarehouseLocation.warehouse_id == warehouse_id,
        LocationStock.company_id == company_id,
        LocationStock.product_id == product_id,
        LocationStock.quantity > 0,
    ).order_by(LocationStock.location_id.asc()).with_for_update().all()

    allocated = sum((as_decimal(row.quantity) for row in location_rows), Decimal('0'))
    unassigned = max(as_decimal(stock.quantity) - allocated, Decimal('0'))
    remaining = max(required_qty - unassigned, Decimal('0'))
    for row in location_rows:
        if remaining <= 0:
            break
        taken = min(as_decimal(row.quantity), remaining)
        row.quantity = as_decimal(row.quantity) - taken
        remaining -= taken
    if remaining > 0:
        raise BusinessRuleError('La distribución por ubicaciones no coincide con el stock del almacén.')
    return stock


def _deduct_requirement(company_id, warehouse_id, product_id, variant_id, quantity, reason, *, sale_id=None, user_id=None):
    available = available_requirement(
        company_id, product_id, warehouse_id, variant_id=variant_id, sale_id=sale_id
    )
    if available < quantity:
        raise BusinessRuleError(f'Stock insuficiente. Disponible {display_quantity(available)}, requerido {display_quantity(quantity)}.')

    parent_stock = _deduct_location_stock(company_id, product_id, warehouse_id, quantity)
    parent_stock.quantity = as_decimal(parent_stock.quantity) - quantity

    if variant_id:
        variant_stock = WarehouseVariantStock.query.filter_by(
            company_id=company_id, warehouse_id=warehouse_id,
            product_id=product_id, variant_id=variant_id,
        ).with_for_update().first()
        if not variant_stock or as_decimal(variant_stock.quantity) < quantity:
            raise BusinessRuleError('El stock de la variante no coincide con el stock general del producto.')
        variant_stock.quantity = as_decimal(variant_stock.quantity) - quantity

    db.session.add(StockMovement(
        company_id=company_id,
        product_id=product_id,
        warehouse_id=warehouse_id,
        movement_type='OUT',
        quantity=quantity,
        reason=reason,
        user_id=user_id,
        created_at=utcnow(),
    ))


def consume_sale_stock(sale):
    """Consume all inventory for a sale, including kits, FEFO and serials."""
    for item in sale.items:
        if is_service(item.product):
            item.cost_snapshot = Decimal('0')
            continue
        requirements = stock_requirements(item)
        item.cost_snapshot = sale_line_unit_cost(item, requirements)
        for product_id, variant_id, qty, label in requirements:
            _deduct_requirement(
                sale.company_id, item.warehouse_id, product_id, variant_id, qty,
                f'Venta #{sale.id}' + (f' · kit {item.product.name}' if product_id != item.product_id else ''),
                sale_id=sale.id, user_id=sale.user_id,
            )
        # Lot/serial traceability belongs to direct product lines. Tracked bundle
        # components are intentionally disallowed when configuring a kit.
        allocate_fefo(item)
        complete_serials_for_item(item)

    for reservation in StockReservation.query.join(
        SaleItem, StockReservation.sale_item_id == SaleItem.id
    ).filter(
        StockReservation.company_id == sale.company_id,
        SaleItem.sale_id == sale.id,
        StockReservation.status == 'ACTIVE',
    ).with_for_update().all():
        reservation.status = 'CONSUMED'


def finalize_sale_inventory_and_loyalty(sale, settings=None):
    consume_sale_stock(sale)
    if sale.client:
        accrue_loyalty(sale.client, sale, settings)
    return sale
