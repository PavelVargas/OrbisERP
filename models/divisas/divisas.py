from services.time_utils import utcnow
# models/divisas/divisas.py
from db import db
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import requests
from flask import current_app

from services.numeric import NumericValueError, bounded_decimal


class ExchangeRate(db.Model):
    __tablename__ = 'exchange_rates'
    
    id = db.Column(db.Integer, primary_key=True)

    currency_code = db.Column(db.String(3), nullable=False)
    symbol = db.Column(db.String(10), nullable=False, default='$')
    rate = db.Column(db.Numeric(18, 8), nullable=False)

    last_update = db.Column(db.DateTime, default=utcnow)

    # MULTIEMPRESA
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    __table_args__ = (
        db.UniqueConstraint('company_id', 'currency_code', name='uq_exchange_rate_company_currency'),
        db.CheckConstraint(
            "rate > 0 AND rate <= 9999999999.99999999",
            name='ck_exchange_rates_rate_range',
        ),
    )


    @staticmethod
    def _validated_rate(value):
        return bounded_decimal(
            value,
            field_name='Tasa de conversión',
            places=8,
            minimum='0.00000001',
            maximum='9999999999.99999999',
        )

    @classmethod
    def get_rate(cls, code, company_id):
        """Obtiene la tasa de conversión desde la DB o la actualiza si es necesario"""
        code = code.upper()

        if code == 'DOP':
            return Decimal('1')
        
        record = cls.query.filter_by(
            currency_code=code,
            company_id=company_id
        ).first()

        if not record or (utcnow() - record.last_update).total_seconds() > 43200:
            return cls.update_from_api(code, company_id)

        try:
            return cls._validated_rate(record.rate)
        except NumericValueError:
            current_app.logger.error(
                'Tasa almacenada inválida para %s en empresa %s', code, company_id
            )
            return cls.update_from_api(code, company_id)


    @classmethod
    def get_rate_or_default(cls, code, company_id, default='1'):
        """Return a verified display rate without turning a provider outage into HTTP 500.

        This helper is intentionally for read-only presentation paths. Financial
        writes must continue using :meth:`get_rate` so a missing non-base rate is
        reported to the user instead of silently storing amounts at a 1:1 rate.
        """
        try:
            return cls.get_rate(code, company_id)
        except (RuntimeError, NumericValueError, InvalidOperation, TypeError, ValueError) as exc:
            current_app.logger.warning(
                'Usando tasa de visualización por defecto para %s en empresa %s: %s',
                code, company_id, exc,
            )
            return cls._validated_rate(default)


    @classmethod
    def update_from_api(cls, code, company_id):
        """Consulta una API externa para mantener los precios actualizados"""
        
        api_key = current_app.config.get('FREECURRENCY_API_KEY', '')
        if not api_key:
            record = cls.query.filter_by(currency_code=code, company_id=company_id).first()
            if record:
                try:
                    return cls._validated_rate(record.rate)
                except NumericValueError as exc:
                    raise RuntimeError(
                        'La tasa almacenada no es válida. Introduce una tasa manualmente.'
                    ) from exc
            raise RuntimeError('Configura FREECURRENCY_API_KEY o introduce la tasa manualmente.')

        url = 'https://api.freecurrencyapi.com/v1/latest'

        try:
            response = requests.get(url, params={'apikey': api_key, 'base_currency': code, 'currencies': 'DOP'}, timeout=5)
            response.raise_for_status()
            data = response.json()

            if 'data' in data and 'DOP' in data['data']:

                try:
                    new_rate = Decimal(str(data['data']['DOP'])).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)
                except (InvalidOperation, TypeError, ValueError, OverflowError) as exc:
                    raise ValueError('La API devolvió una tasa no válida.') from exc
                if not new_rate.is_finite() or new_rate <= 0 or new_rate > Decimal('9999999999.99999999'):
                    raise ValueError('La API devolvió una tasa fuera de rango.')

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
                    record.last_update = utcnow()

                db.session.commit()
                return new_rate

            else:
                raise ValueError("Formato de API incorrecto")

        except Exception as e:

            current_app.logger.warning('No se pudo actualizar la divisa %s: %s', code, e)

            record = cls.query.filter_by(
                currency_code=code,
                company_id=company_id
            ).first()

            if record:
                try:
                    return cls._validated_rate(record.rate)
                except NumericValueError:
                    pass

            raise RuntimeError('No se obtuvo una tasa verificable. Introduce la tasa manualmente.') from e


    def __repr__(self):
        return f"<ExchangeRate {self.currency_code}: {self.rate}>"
