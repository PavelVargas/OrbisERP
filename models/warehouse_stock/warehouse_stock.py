from db import db

class WarehouseStock(db.Model):
    __tablename__ = 'warehouse_stock'

    id = db.Column(db.Integer, primary_key=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, default=0)

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
