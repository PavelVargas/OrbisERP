from db import db

class SaleItem(db.Model):
    __tablename__ = 'sale_items'
    __table_args__ = (
        db.CheckConstraint('quantity > 0', name='ck_sale_items_quantity_positive'),
        db.CheckConstraint('price >= 0', name='ck_sale_items_price_nonnegative'),
    )

    id = db.Column(db.Integer, primary_key=True)

    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=True)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'), nullable=True, index=True)
    uom_id = db.Column(db.Integer, db.ForeignKey('units_of_measure.id'), nullable=True)
    uom_factor = db.Column(db.Numeric(18, 6), nullable=False, default=1)

    quantity = db.Column(db.Numeric(14, 3), nullable=False)
    price = db.Column(db.Numeric(10,2), nullable=False)
    cost_snapshot = db.Column(db.Numeric(12,4), nullable=False, default=0)
    tax_name = db.Column(db.String(80), nullable=False, default='ITBIS 18%')
    tax_rate = db.Column(db.Numeric(5,2), nullable=False, default=18)
    tax_included = db.Column(db.Boolean, nullable=False, default=True)

    product = db.relationship('Product')
    warehouse = db.relationship('Warehouse')
    variant = db.relationship('ProductVariant')
    uom = db.relationship('UnitOfMeasure')
