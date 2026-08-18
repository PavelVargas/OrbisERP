from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from models.divisas.divisas import ExchangeRate
from models.user.user import User
from db import db
from datetime import datetime

divisas_bp = Blueprint('divisas_bp', __name__)


@divisas_bp.route('/divisas')
def listar_divisas():
    user_id = session.get('user_id')
    company_id = session.get('company_id')

    if not user_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get(user_id)

    if not user.has_permission('currencies.view'):
        flash('No tienes permisos para ver divisas', 'danger')
        return redirect(url_for('dashboard_bp.dashboard'))

    # SOLO DIVISAS DE LA EMPRESA
    divisas = ExchangeRate.query.filter_by(company_id=company_id).all()

    return render_template('divisas/gestion.html', divisas=divisas, user=user)


@divisas_bp.route('/divisas/crear', methods=['POST'])
def crear_divisa():

    user_id = session.get('user_id')
    company_id = session.get('company_id')

    if not user_id:
        return redirect(url_for('login_bp.login'))

    code = request.form.get('currency_code').upper()
    symbol = request.form.get('symbol')

    # VERIFICAR SI EXISTE EN ESTA EMPRESA
    existing = ExchangeRate.query.filter_by(
        currency_code=code,
        company_id=company_id
    ).first()

    if existing:
        flash(f'La divisa {code} ya está registrada', 'warning')
        return redirect(url_for('divisas_bp.listar_divisas'))

    rate = ExchangeRate.get_rate(code, company_id)

    new_currency = ExchangeRate(
        currency_code=code,
        symbol=symbol,
        rate=rate,
        company_id=company_id
    )

    db.session.add(new_currency)
    db.session.commit()

    flash(f'Divisa {code} agregada con éxito', 'success')

    return redirect(url_for('divisas_bp.listar_divisas'))


@divisas_bp.route('/divisas/editar/<int:id>', methods=['POST'])
def editar_divisa(id):

    user_id = session.get('user_id')
    company_id = session.get('company_id')

    if not user_id:
        return redirect(url_for('login_bp.login'))

    divisa = ExchangeRate.query.filter_by(id=id, company_id=company_id).first_or_404()

    nuevo_codigo = request.form.get('currency_code').upper()
    nuevo_simbolo = request.form.get('symbol')

    try:

        if divisa.currency_code != nuevo_codigo and nuevo_codigo != 'DOP':

            nueva_tasa = ExchangeRate.get_rate(nuevo_codigo, company_id)

            if nueva_tasa:
                divisa.rate = nueva_tasa

        divisa.currency_code = nuevo_codigo
        divisa.symbol = nuevo_simbolo
        divisa.last_update = datetime.utcnow()

        db.session.commit()

        flash(f'Divisa {nuevo_codigo} actualizada correctamente.', 'success')

    except Exception as e:

        db.session.rollback()

        flash(f'Error al actualizar: {str(e)}', 'danger')

    return redirect(url_for('divisas_bp.listar_divisas'))


@divisas_bp.route('/divisas/eliminar/<int:id>', methods=['POST'])
def eliminar_divisa(id):

    user_id = session.get('user_id')
    company_id = session.get('company_id')

    if not user_id:
        return redirect(url_for('login_bp.login'))

    user = User.query.get_or_404(user_id)
    if not user.has_permission('currencies.manage'):
        return redirect(url_for('dashboard_bp.dashboard'))
    divisa = ExchangeRate.query.filter_by(id=id, company_id=company_id).first_or_404()

    if divisa.currency_code == 'DOP':
        flash('No se puede eliminar la moneda base del sistema.', 'warning')
        return redirect(url_for('divisas_bp.listar_divisas'))

    try:

        db.session.delete(divisa)
        db.session.commit()

        flash('Divisa eliminada con éxito.', 'success')

    except Exception:

        db.session.rollback()

        flash('Error al eliminar la divisa.', 'danger')

    return redirect(url_for('divisas_bp.listar_divisas'))
