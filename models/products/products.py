from datetime import datetime
import enum
from db import db

class ProductType(enum.Enum):
    STOCKED = "con_stock"    
    SERVICE = "servicio"      
    CONSUMABLE = "consumible" 

class Product(db.Model):
    __tablename__ = 'products'
    __table_args__ = (
        db.UniqueConstraint('company_id', 'sku', name='uq_products_company_sku'),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    sku = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text)
    image_path = db.Column(db.String(255), nullable=True)
    
    price = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    cost = db.Column(db.Numeric(10, 2), nullable=False, default=0.00) 
    
    status = db.Column(db.Boolean, default=True)
    product_type = db.Column(
        db.Enum(ProductType), 
        default=ProductType.STOCKED, 
        nullable=False
    )

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
        """
        Calcula el stock total. Si el producto es un servicio, 
        siempre retorna 0 evitando consultas innecesarias.
        """
        if self.product_type == ProductType.SERVICE:
            return 0
        return sum(ws.quantity for ws in self.stocks)

    def __repr__(self):
        return f'<Product {self.name} ({self.sku}) - Type: {self.product_type.value}>'
