from services.time_utils import utcnow
from datetime import datetime
from db import db

class StockMovement(db.Model):
    __tablename__ = 'stock_movements'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    
    # Nuevo: Identificador de empresa
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)

    movement_type = db.Column(db.String(10), nullable=False)  # IN / OUT
    quantity = db.Column(db.Numeric(14, 3), nullable=False)
    reason = db.Column(db.String(100)) 
    created_at = db.Column(db.DateTime, default=utcnow)

    product = db.relationship('Product', backref='stock_movements_ref')
    warehouse = db.relationship('Warehouse', backref='stock_movements_ref')
    user = db.relationship('User', backref='stock_movements')

    def __repr__(self):
        return f'<StockMovement {self.movement_type} {self.quantity}>'
