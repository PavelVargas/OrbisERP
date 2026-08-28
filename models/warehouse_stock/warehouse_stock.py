from db import db

class WarehouseStock(db.Model):
    __tablename__ = 'warehouse_stock'
    __table_args__ = (
        db.CheckConstraint('quantity >= 0', name='ck_warehouse_stock_quantity_nonnegative'),
        db.UniqueConstraint('company_id', 'warehouse_id', 'product_id', name='uq_warehouse_stock_tenant_product'),
    )

    id = db.Column(db.Integer, primary_key=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Numeric(14, 3), nullable=False, default=0)

    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)

    # 🔗 PRODUCT
    product = db.relationship(
        'Product',
        back_populates='stocks'
    )

    # 🔗 WAREHOUSE (ÚNICA)
    warehouse = db.relationship(
        'Warehouse',
        back_populates='stocks'
    )

    def __repr__(self):
        return f'<WarehouseStock P:{self.product_id} W:{self.warehouse_id} Q:{self.quantity}>'
