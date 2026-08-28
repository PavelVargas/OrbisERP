from services.time_utils import utcnow
from datetime import datetime

from db import db


class WarehouseLocation(db.Model):
    __tablename__ = 'warehouse_locations'
    __table_args__ = (
        db.UniqueConstraint('company_id', 'barcode', name='uq_location_company_barcode'),
        db.UniqueConstraint('warehouse_id', 'code', name='uq_location_warehouse_code'),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    code = db.Column(db.String(50), nullable=False)
    barcode = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    status = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('warehouse_locations.id'), nullable=True)

    warehouse = db.relationship('Warehouse', back_populates='locations')
    parent = db.relationship(
        'WarehouseLocation',
        remote_side=[id],
        back_populates='children',
        foreign_keys=[parent_id],
    )
    children = db.relationship(
        'WarehouseLocation',
        back_populates='parent',
        cascade='all, delete-orphan',
        single_parent=True,
    )
    stocks = db.relationship(
        'LocationStock',
        back_populates='location',
        cascade='all, delete-orphan',
    )

    @property
    def full_path(self):
        parts = []
        current = self
        visited = set()
        while current and current.id not in visited:
            visited.add(current.id)
            parts.append(current.name)
            current = current.parent
        return ' / '.join(reversed(parts))

    @property
    def depth(self):
        level = 0
        current = self.parent
        visited = set()
        while current and current.id not in visited:
            visited.add(current.id)
            level += 1
            current = current.parent
        return min(level, 5)

    def __repr__(self):
        return f'<WarehouseLocation {self.full_path} [{self.barcode}]>'


class LocationStock(db.Model):
    __tablename__ = 'location_stock'
    __table_args__ = (
        db.UniqueConstraint('location_id', 'product_id', name='uq_location_product_stock'),
    )

    id = db.Column(db.Integer, primary_key=True)
    location_id = db.Column(db.Integer, db.ForeignKey('warehouse_locations.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    quantity = db.Column(db.Numeric(14, 3), nullable=False, default=0)

    location = db.relationship('WarehouseLocation', back_populates='stocks')
    product = db.relationship('Product')

    def __repr__(self):
        return f'<LocationStock L:{self.location_id} P:{self.product_id} Q:{self.quantity}>'


class LocationMovement(db.Model):
    __tablename__ = 'location_movements'

    id = db.Column(db.Integer, primary_key=True)
    movement_type = db.Column(db.String(20), nullable=False)
    quantity = db.Column(db.Numeric(14, 3), nullable=False)
    balance_after = db.Column(db.Numeric(14, 3), nullable=False)
    reference = db.Column(db.String(80), nullable=True)
    notes = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    location_id = db.Column(db.Integer, db.ForeignKey('warehouse_locations.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    transfer_id = db.Column(db.Integer, db.ForeignKey('stock_transfers.id'), nullable=True)

    location = db.relationship('WarehouseLocation')
    product = db.relationship('Product')
    user = db.relationship('User')
    transfer = db.relationship('StockTransfer')
