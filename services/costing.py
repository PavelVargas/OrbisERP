"""Inventory costing for retail receipts and sales."""
from __future__ import annotations

from decimal import Decimal

from db import db
from models.retail import InventoryCostLayer
from services.quantity import as_decimal
from services.retail import get_retail_settings


def register_receipt_cost(product, warehouse_id, quantity, unit_cost, *, variant_id=None, purchase_item_id=None):
    company_id = product.company_id
    qty = as_decimal(quantity)
    cost = as_decimal(unit_cost).quantize(Decimal('0.0001'))
    settings = get_retail_settings(company_id, create=True)
    method = (settings.costing_method or 'AVERAGE').upper()

    # Always keep layers: they provide an audit trail and permit changing to FIFO
    # later without losing the receipt history.
    db.session.add(InventoryCostLayer(
        company_id=company_id, product_id=product.id, variant_id=variant_id,
        warehouse_id=warehouse_id, purchase_item_id=purchase_item_id,
        quantity_remaining=qty, unit_cost=cost,
    ))

    if method == 'LAST':
        product.cost = cost.quantize(Decimal('0.01'))
        return product.cost

    if method == 'AVERAGE':
        from models.warehouse_stock.warehouse_stock import WarehouseStock
        # Call this before adding receipt quantity to stock. Existing stock across
        # warehouses is valued at the current average product cost.
        rows = WarehouseStock.query.filter_by(company_id=company_id, product_id=product.id).all()
        old_qty = sum((as_decimal(row.quantity) for row in rows), Decimal('0'))
        old_value = old_qty * as_decimal(product.cost)
        new_qty = old_qty + qty
        if new_qty > 0:
            product.cost = ((old_value + qty * cost) / new_qty).quantize(Decimal('0.01'))
        return product.cost

    # FIFO does not overwrite historical layers. product.cost remains a useful
    # display/reference value using latest receipt while cost_snapshot uses FIFO.
    product.cost = cost.quantize(Decimal('0.01'))
    return product.cost


def consume_fifo_cost(company_id, product_id, warehouse_id, quantity, *, variant_id=None):
    needed = as_decimal(quantity)
    layers = InventoryCostLayer.query.filter(
        InventoryCostLayer.company_id == company_id,
        InventoryCostLayer.product_id == product_id,
        InventoryCostLayer.warehouse_id == warehouse_id,
        InventoryCostLayer.quantity_remaining > 0,
    )
    if variant_id:
        layers = layers.filter(InventoryCostLayer.variant_id == variant_id)
    else:
        layers = layers.filter(InventoryCostLayer.variant_id.is_(None))
    layers = layers.order_by(InventoryCostLayer.received_at.asc(), InventoryCostLayer.id.asc()).with_for_update().all()
    total_cost = Decimal('0')
    consumed = Decimal('0')
    for layer in layers:
        if needed <= 0:
            break
        take = min(as_decimal(layer.quantity_remaining), needed)
        total_cost += take * as_decimal(layer.unit_cost)
        consumed += take
        layer.quantity_remaining = as_decimal(layer.quantity_remaining) - take
        needed -= take
    return total_cost, consumed, needed


def sale_line_unit_cost(item, requirements):
    """Return commercial-line unit cost and consume FIFO layers when enabled."""
    settings = get_retail_settings(item.sale.company_id, create=True)
    method = (settings.costing_method or 'AVERAGE').upper()
    line_qty = as_decimal(item.quantity)
    if line_qty <= 0:
        return Decimal('0')
    total = Decimal('0')
    for product_id, variant_id, qty, _label in requirements:
        from models.products.products import Product
        product = db.session.get(Product, product_id)
        if method == 'FIFO':
            fifo_cost, consumed, missing = consume_fifo_cost(
                item.sale.company_id, product_id, item.warehouse_id, qty, variant_id=variant_id
            )
            if missing > 0:
                fifo_cost += missing * as_decimal(product.cost)
            total += fifo_cost
        else:
            unit = as_decimal(product.cost)
            if variant_id:
                from models.retail import ProductVariant
                variant = db.session.get(ProductVariant, variant_id)
                if variant:
                    unit += as_decimal(variant.cost_extra)
            total += qty * unit
    return (total / line_qty).quantize(Decimal('0.0001'))
