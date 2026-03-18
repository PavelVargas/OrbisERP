# models/divisas/divisas.py
from db import db
from datetime import datetime
import requests


class ExchangeRate(db.Model):
    __tablename__ = 'exchange_rates'
    
    id = db.Column(db.Integer, primary_key=True)

    currency_code = db.Column(db.String(3), nullable=False)
    symbol = db.Column(db.String(10), nullable=False, default='$')
    rate = db.Column(db.Float, nullable=False)

    last_update = db.Column(db.DateTime, default=datetime.utcnow)

    # MULTIEMPRESA
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)


    @classmethod
    def get_rate(cls, code, company_id):
        """Obtiene la tasa de conversión desde la DB o la actualiza si es necesario"""
        code = code.upper()

        if code == 'DOP':
            return 1.0
        
        record = cls.query.filter_by(
            currency_code=code,
            company_id=company_id
        ).first()

        if not record or (datetime.utcnow() - record.last_update).total_seconds() > 43200:
            return cls.update_from_api(code, company_id)

        return record.rate


    @classmethod
    def update_from_api(cls, code, company_id):
        """Consulta una API externa para mantener los precios actualizados"""
        
        API_KEY = 'fca_live_tu_clave_aqui'

        url = f"https://api.freecurrencyapi.com/v1/latest?apikey={API_KEY}&base_currency={code}&currencies=DOP"

        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()

            if 'data' in data and 'DOP' in data['data']:

                new_rate = data['data']['DOP']

                record = cls.query.filter_by(
                    currency_code=code,
                    company_id=company_id
                ).first()

                if not record:
                    record = cls(
                        currency_code=code,
                        rate=new_rate,
                        symbol='$',
                        company_id=company_id
                    )
                    db.session.add(record)

                else:
                    record.rate = new_rate
                    record.last_update = datetime.utcnow()

                db.session.commit()
                return new_rate

            else:
                raise ValueError("Formato de API incorrecto")

        except Exception as e:

            print(f"!!! Error actualizando divisa {code}: {e}")

            record = cls.query.filter_by(
                currency_code=code,
                company_id=company_id
            ).first()

            if record:
                return record.rate

            defaults = {
                'USD': 58.50,
                'MXN': 3.45,
                'ARS': 0.06,
                'COP': 0.015,
                'EUR': 63.20
            }

            return defaults.get(code, 1.0)


    def __repr__(self):
        return f"<ExchangeRate {self.currency_code}: {self.rate}>"