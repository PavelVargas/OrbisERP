from datetime import datetime
from db import db

class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    sku = db.Column(db.String(50), nullable=False) 
    description = db.Column(db.Text)
    

    price = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    cost = db.Column(db.Numeric(10, 2), nullable=False, default=0.00) # ✅ Campo añadido
    
    status = db.Column(db.Boolean, default=True)

    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)

    category = db.relationship('Category', backref='products')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    stocks = db.relationship(
        'WarehouseStock',
        back_populates='product',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )

    @property
    def total_stock(self):
        return sum(ws.quantity for ws in self.stocks)

    def __repr__(self):
        return f'<Product {self.name} ({self.sku})>'