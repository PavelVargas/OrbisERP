from services.time_utils import utcnow
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
        db.CheckConstraint("sale_mode IN ('UNIT','WEIGHT')", name='ck_products_sale_mode'),
        db.CheckConstraint("tracking IN ('NONE','LOT','SERIAL')", name='ck_products_tracking'),
        db.CheckConstraint('warranty_days >= 1', name='ck_products_warranty_days'),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    sku = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text)
    image_path = db.Column(db.String(255), nullable=True)
    image_url = db.Column(db.String(2048), nullable=True)
    archived_at = db.Column(db.DateTime, nullable=True, index=True)
    
    price = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    cost = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    min_stock = db.Column(db.Numeric(14, 3), nullable=False, default=5)
    max_stock = db.Column(db.Numeric(14, 3), nullable=True)
    
    status = db.Column(db.Boolean, default=True)
    product_type = db.Column(
        db.Enum(ProductType), 
        default=ProductType.STOCKED, 
        nullable=False
    )

    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    sales_tax_id = db.Column(db.Integer, db.ForeignKey('sales_taxes.id'), nullable=True)
    brand = db.Column(db.String(100), nullable=True)
    sale_mode = db.Column(db.String(20), nullable=False, default='UNIT')
    tracking = db.Column(db.String(20), nullable=False, default='NONE')
    warranty_days = db.Column(db.Integer, nullable=False, default=30)
    base_uom_id = db.Column(db.Integer, db.ForeignKey('units_of_measure.id'), nullable=True)
    sale_uom_id = db.Column(db.Integer, db.ForeignKey('units_of_measure.id'), nullable=True)
    purchase_uom_id = db.Column(db.Integer, db.ForeignKey('units_of_measure.id'), nullable=True)

    category = db.relationship('Category', backref='products')
    sales_tax = db.relationship('SalesTax')
    base_uom = db.relationship('UnitOfMeasure', foreign_keys=[base_uom_id])
    sale_uom = db.relationship('UnitOfMeasure', foreign_keys=[sale_uom_id])
    purchase_uom = db.relationship('UnitOfMeasure', foreign_keys=[purchase_uom_id])
    created_at = db.Column(db.DateTime, default=utcnow)

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
        from decimal import Decimal
        return sum((Decimal(ws.quantity or 0) for ws in self.stocks), Decimal('0'))

    def __repr__(self):
        return f'<Product {self.name} ({self.sku}) - Type: {self.product_type.value}>'
