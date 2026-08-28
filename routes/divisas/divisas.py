import re

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from sqlalchemy.exc import IntegrityError

from db import db
from models.divisas.divisas import ExchangeRate
from models.user.user import User
from services.numeric import NumericValueError, bounded_decimal
from services.time_utils import utcnow


divisas_bp = Blueprint('divisas_bp', __name__)
_RATE_MAX = '9999999999.99999999'


def _context(permission):
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    if not user_id or not company_id:
        return None, None, redirect(url_for('login_bp.login'))
    user = User.query.filter_by(id=user_id, company_id=company_id, is_active=True).first()
    if not user:
        session.clear()
        return None, None, redirect(url_for('login_bp.login'))
    if not user.has_permission(permission):
        flash('No tienes permisos para realizar esta operación.', 'danger')
        return None, None, redirect(url_for('dashboard_bp.dashboard'))
    return user, company_id, None


def _identity(form):
    code = (form.get('currency_code') or '').strip().upper()
    symbol = (form.get('symbol') or '').strip()
    if not re.fullmatch(r'[A-Z]{3}', code):
        raise NumericValueError('El código debe contener exactamente tres letras ISO.')
    if not symbol or len(symbol) > 10 or any(char in symbol for char in '\r\n\x00'):
        raise NumericValueError('El símbolo es obligatorio y admite hasta 10 caracteres.')
    return code, symbol


def _rate(value, *, code, company_id):
    if code == 'DOP':
        return bounded_decimal('1', field_name='Tasa', places=8, minimum='0.00000001', maximum=_RATE_MAX)
    raw = (value or '').strip()
    if not raw:
        raw = ExchangeRate.get_rate(code, company_id)
    return bounded_decimal(
        raw,
        field_name='Tasa',
        places=8,
        minimum='0.00000001',
        maximum=_RATE_MAX,
    )


@divisas_bp.route('/divisas')
def listar_divisas():
    user, company_id, denied = _context('currencies.view')
    if denied:
        return denied
    divisas = ExchangeRate.query.filter_by(company_id=company_id).order_by(ExchangeRate.currency_code.asc()).all()
    return render_template(
        'divisas/gestion.html', divisas=divisas, user=user,
        current_currency=session.get('selected_currency', 'DOP'),
    )


@divisas_bp.route('/divisas/crear', methods=['POST'])
def crear_divisa():
    _, company_id, denied = _context('currencies.manage')
    if denied:
        return denied
    try:
        code, symbol = _identity(request.form)
        if ExchangeRate.query.filter_by(currency_code=code, company_id=company_id).first():
            flash(f'La divisa {code} ya está registrada.', 'warning')
            return redirect(url_for('divisas_bp.listar_divisas'))
        rate = _rate(request.form.get('rate'), code=code, company_id=company_id)
        db.session.add(ExchangeRate(currency_code=code, symbol=symbol, rate=rate, company_id=company_id))
        db.session.commit()
    except NumericValueError as exc:
        db.session.rollback()
        flash(str(exc), 'danger')
        return redirect(url_for('divisas_bp.listar_divisas'))
    except RuntimeError as exc:
        db.session.rollback()
        flash(str(exc), 'danger')
        return redirect(url_for('divisas_bp.listar_divisas'))
    except IntegrityError:
        db.session.rollback()
        flash('La divisa ya existe o sus datos no cumplen las restricciones.', 'warning')
        return redirect(url_for('divisas_bp.listar_divisas'))
    except Exception:
        db.session.rollback()
        current_app.logger.exception('No se pudo crear una divisa')
        flash('No fue posible registrar la divisa.', 'danger')
        return redirect(url_for('divisas_bp.listar_divisas'))
    flash(f'Divisa {code} agregada con éxito.', 'success')
    return redirect(url_for('divisas_bp.listar_divisas'))


@divisas_bp.route('/divisas/editar/<int:id>', methods=['POST'])
def editar_divisa(id):
    _, company_id, denied = _context('currencies.manage')
    if denied:
        return denied
    divisa = ExchangeRate.query.filter_by(id=id, company_id=company_id).first_or_404()
    try:
        code, symbol = _identity(request.form)
        raw_rate = request.form.get('rate')
        if not (raw_rate or '').strip() and divisa.currency_code == code:
            rate = bounded_decimal(
                divisa.rate,
                field_name='Tasa', places=8, minimum='0.00000001', maximum=_RATE_MAX,
            )
        else:
            rate = _rate(raw_rate, code=code, company_id=company_id)
        divisa.currency_code = code
        divisa.symbol = symbol
        divisa.rate = rate
        divisa.last_update = utcnow()
        db.session.commit()
    except NumericValueError as exc:
        db.session.rollback()
        flash(str(exc), 'danger')
        return redirect(url_for('divisas_bp.listar_divisas'))
    except RuntimeError as exc:
        db.session.rollback()
        flash(str(exc), 'danger')
        return redirect(url_for('divisas_bp.listar_divisas'))
    except IntegrityError:
        db.session.rollback()
        flash('Ya existe una divisa con ese código en la empresa.', 'warning')
        return redirect(url_for('divisas_bp.listar_divisas'))
    except Exception:
        db.session.rollback()
        current_app.logger.exception('No se pudo actualizar la divisa %s', id)
        flash('No fue posible actualizar la divisa.', 'danger')
        return redirect(url_for('divisas_bp.listar_divisas'))
    flash(f'Divisa {code} actualizada correctamente.', 'success')
    return redirect(url_for('divisas_bp.listar_divisas'))


@divisas_bp.route('/divisas/eliminar/<int:id>', methods=['POST'])
def eliminar_divisa(id):
    _, company_id, denied = _context('currencies.manage')
    if denied:
        return denied
    divisa = ExchangeRate.query.filter_by(id=id, company_id=company_id).first_or_404()
    if divisa.currency_code == 'DOP':
        flash('No se puede eliminar la moneda base del sistema.', 'warning')
        return redirect(url_for('divisas_bp.listar_divisas'))
    try:
        db.session.delete(divisa)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash('La divisa está en uso y no puede eliminarse.', 'danger')
        return redirect(url_for('divisas_bp.listar_divisas'))
    except Exception:
        db.session.rollback()
        current_app.logger.exception('No se pudo eliminar la divisa %s', id)
        flash('No fue posible eliminar la divisa.', 'danger')
        return redirect(url_for('divisas_bp.listar_divisas'))
    flash('Divisa eliminada con éxito.', 'success')
    return redirect(url_for('divisas_bp.listar_divisas'))
