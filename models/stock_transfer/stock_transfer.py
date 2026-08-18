from db import db
from datetime import datetime

class StockTransfer(db.Model):
    __tablename__ = 'stock_transfers'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    from_warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    to_warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    from_location_id = db.Column(db.Integer, db.ForeignKey('warehouse_locations.id'), nullable=True)
    to_location_id = db.Column(db.Integer, db.ForeignKey('warehouse_locations.id'), nullable=True)
    
    # Nuevo: Identificador de empresa
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)

    quantity = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='PENDING')  # PENDING / RECEIVED
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    product = db.relationship('Product')
    from_warehouse = db.relationship('Warehouse', foreign_keys=[from_warehouse_id])
    to_warehouse = db.relationship('Warehouse', foreign_keys=[to_warehouse_id])
    from_location = db.relationship('WarehouseLocation', foreign_keys=[from_location_id])
    to_location = db.relationship('WarehouseLocation', foreign_keys=[to_location_id])

    def __repr__(self):
        return f'<StockTransfer {self.id} Qty:{self.quantity}>'
