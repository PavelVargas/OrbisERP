from db import db

class Warehouse(db.Model):
    __tablename__ = 'warehouses'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    location = db.Column(db.String(255), nullable=True) 
    status = db.Column(db.Boolean, default=True)
    is_main = db.Column(db.Boolean, default=False) 

    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)

    stocks = db.relationship(
        'WarehouseStock',
        back_populates='warehouse',
        cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f'<Warehouse {self.name}>'