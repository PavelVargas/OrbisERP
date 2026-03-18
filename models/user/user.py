from db import db

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), nullable=False, unique=True)
    password = db.Column(db.String(150), nullable=False)
    cedula = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(150), nullable=False, default="user")

    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=True)
    assigned_warehouse = db.relationship('Warehouse', backref='assigned_users')
    default_currency = db.Column(db.String(3), default='DOP', nullable=False)
    
    company_id = db.Column(
        db.Integer,
        db.ForeignKey('companies.id'),
        nullable=True
    )

    def __repr__(self):
        return f'<User {self.name} - {self.role}>'
