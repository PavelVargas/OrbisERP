from services.numeric import NumericValueError, bounded_decimal, finite_decimal
from services.time_utils import utcnow
from flask import Blueprint, abort, render_template, request, redirect, url_for, flash, session
from models.sales.sales import Sale
from models.cash.cash_closing import CashClosing
from models.user.user import User
from models.divisas.divisas import ExchangeRate
from models.productivity import CashSession
from models.backoffice import Expense
from models.retail import Branch, PosTerminal
from db import db
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from decimal import Decimal, ROUND_HALF_UP

cash_bp = Blueprint('cash_bp', __name__, url_prefix='/cash')


def _currency_context(company_id):
    code = session.get('selected_currency', 'DOP')
    row = ExchangeRate.query.filter_by(currency_code=code, company_id=company_id).first()
    if not row:
        row = ExchangeRate.query.filter_by(company_id=company_id).order_by(ExchangeRate.id.asc()).first()
    rate = finite_decimal(str(row.rate)) if row and row.rate else finite_decimal('1')
    if rate <= 0:
        rate = finite_decimal('1')
    return (row.currency_code if row else code), (row.symbol if row else 'RD$'), rate


def _cash_branch_context(company_id, user):
    """Resolve the branch represented by this cash screen.

    Operational users are always locked to their assigned branch/terminal. Admins
    may switch among active branches so one cash session never represents the
    whole company accidentally.
    """
    branches = Branch.query.filter_by(company_id=company_id, status=True).order_by(
        Branch.is_main.desc(), Branch.name.asc()
    ).all()
    terminal = None
    forced_branch = None
    if user and user.terminal_id:
        terminal = PosTerminal.query.filter_by(
            id=user.terminal_id, company_id=company_id, status=True
        ).first()
        if terminal and terminal.branch_id:
            forced_branch = terminal.branch
    if not forced_branch and user and user.branch_id:
        forced_branch = next((branch for branch in branches if branch.id == user.branch_id), None)

    requested_branch_id = request.values.get('branch_id', type=int)
    branch = forced_branch
    if not branch and requested_branch_id:
        branch = next((row for row in branches if row.id == requested_branch_id), None)
    if not branch and session.get('cash_branch_id'):
        branch = next((row for row in branches if row.id == session.get('cash_branch_id')), None)
    if not branch and branches:
        branch = branches[0]

    if branch:
        session['cash_branch_id'] = branch.id
    else:
        session.pop('cash_branch_id', None)
    if terminal and branch and terminal.branch_id != branch.id:
        terminal = None
    return branches, branch, terminal, bool(forced_branch)


def _open_cash_session(company_id, user_id, branch_id):
    if not branch_id:
        return None
    return CashSession.query.filter_by(
        company_id=company_id, user_id=user_id, branch_id=branch_id, status='OPEN'
    ).first()


def _cash_session_totals(cash_session):
    sales_query = db.session.query(func.coalesce(func.sum(Sale.amount_paid), 0)).filter(
        Sale.company_id == cash_session.company_id,
        Sale.user_id == cash_session.user_id,
        Sale.branch_id == cash_session.branch_id,
        Sale.status == 'COMPLETED',
        Sale.payment_method == 'CASH',
        Sale.created_at >= cash_session.opened_at,
    )
    if cash_session.terminal_id:
        sales_query = sales_query.filter(Sale.terminal_id == cash_session.terminal_id)
    cash_sales = sales_query.scalar() or finite_decimal('0')

    cash_expenses = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.company_id == cash_session.company_id,
        Expense.user_id == cash_session.user_id,
        Expense.branch_id == cash_session.branch_id,
        func.upper(Expense.payment_method) == 'CASH',
        Expense.created_at >= cash_session.opened_at,
        Expense.status == 'POSTED',
    ).scalar() or finite_decimal('0')
    expected = finite_decimal(cash_session.opening_amount or 0) + finite_decimal(cash_sales) - finite_decimal(cash_expenses)
    return finite_decimal(cash_sales), finite_decimal(cash_expenses), expected


@cash_bp.route('/register', methods=['GET', 'POST'])
def register():
    company_id, user_id = session.get('company_id'), session.get('user_id')
    if not company_id or not user_id:
        return redirect(url_for('login_bp.login'))
    user = db.session.get(User, user_id)
    selected_currency, currency_symbol, conversion_rate = _currency_context(company_id)
    branches, branch, terminal, branch_locked = _cash_branch_context(company_id, user)
    cash_session = _open_cash_session(company_id, user_id, branch.id if branch else None)

    if request.method == 'POST':
        action = (request.form.get('action') or '').lower()
        if not branch:
            flash('No hay una sucursal activa para esta caja. Configura una sucursal y asígnala al usuario/terminal antes de operar.', 'danger')
            return redirect(url_for('cash_bp.register'))

        if action == 'open':
            if not user or not user.has_permission('cash.open'):
                abort(403)
            if cash_session:
                flash(f'Ya tienes una caja abierta en {branch.name}. Ciérrala antes de abrir otro turno en esta sucursal.', 'warning')
                return redirect(url_for('cash_bp.register', branch_id=branch.id))
            try:
                opening_display = bounded_decimal(
                    request.form.get('opening_amount') or '0',
                    field_name='Fondo inicial', places=2, minimum='0', maximum='9999999999.99',
                )
                opening = (opening_display * conversion_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            except NumericValueError as exc:
                flash(str(exc), 'danger')
                return redirect(url_for('cash_bp.register', branch_id=branch.id))
            db.session.add(CashSession(
                company_id=company_id,
                user_id=user_id,
                branch_id=branch.id,
                terminal_id=terminal.id if terminal else None,
                opening_amount=opening,
                status='OPEN',
            ))
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash(f'Ya existe una caja abierta para tu usuario en {branch.name}.', 'warning')
                return redirect(url_for('cash_bp.register', branch_id=branch.id))
            terminal_text = f' · {terminal.name}' if terminal else ''
            flash(f'Caja abierta en {branch.name}{terminal_text}. Las demás sucursales no se modifican.', 'success')
            return redirect(url_for('cash_bp.register', branch_id=branch.id))

        if action == 'close':
            if not user or not user.has_permission('cash.close'):
                abort(403)
            if not cash_session:
                flash(f'No tienes una caja abierta en {branch.name}.', 'warning')
                return redirect(url_for('cash_bp.register', branch_id=branch.id))
            try:
                counted_display = bounded_decimal(
                    request.form.get('counted_amount'),
                    field_name='Efectivo contado', places=2, minimum='0', maximum='9999999999.99',
                )
                counted = (counted_display * conversion_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            except NumericValueError as exc:
                flash(str(exc), 'danger')
                return redirect(url_for('cash_bp.register', branch_id=branch.id))
            cash_sales, cash_expenses, expected = _cash_session_totals(cash_session)
            difference = counted - expected
            now = utcnow()
            cash_session.expected_amount = expected
            cash_session.counted_amount = counted
            cash_session.difference = difference
            cash_session.notes = (request.form.get('notes') or '').strip()[:1000] or None
            cash_session.status = 'CLOSED'
            cash_session.closed_at = now
            db.session.add(CashClosing(
                company_id=company_id,
                user_id=user_id,
                branch_id=cash_session.branch_id,
                terminal_id=cash_session.terminal_id,
                opening_date=cash_session.opened_at,
                closing_date=now,
                system_amount=expected,
                reported_amount=counted,
                difference=difference,
                notes=(
                    f'Caja #{cash_session.id} · sucursal {branch.name}. '
                    f'Ventas efectivo: {cash_sales}; gastos efectivo: {cash_expenses}. '
                    f'{cash_session.notes or ""}'
                )[:2000],
            ))
            db.session.commit()
            if abs(difference) < finite_decimal('0.01'):
                flash(f'Arqueo correcto en {branch.name}: caja cuadrada.', 'success')
            else:
                flash(
                    f'Arqueo de {branch.name} cerrado con diferencia de '
                    f'{currency_symbol} {(difference / conversion_rate):,.2f}.',
                    'warning',
                )
            return redirect(url_for('cash_bp.register', branch_id=branch.id))

    history_query = CashSession.query.filter_by(company_id=company_id, user_id=user_id)
    if branch:
        history_query = history_query.filter(CashSession.branch_id == branch.id)
    history = history_query.order_by(CashSession.opened_at.desc()).limit(12).all()
    cash_sales = cash_expenses = expected = finite_decimal('0')
    if cash_session:
        cash_sales, cash_expenses, expected = _cash_session_totals(cash_session)
    return render_template(
        'cash/register.html',
        user=user,
        cash_session=cash_session,
        cash_sales=cash_sales,
        cash_expenses=cash_expenses,
        expected=expected,
        history=history,
        branches=branches,
        branch=branch,
        terminal=terminal,
        branch_locked=branch_locked,
        selected_currency=selected_currency,
        currency_symbol=currency_symbol,
        conversion_rate=conversion_rate,
    )


@cash_bp.route('/close', methods=['GET', 'POST'])
def close_cash():
    flash('El cierre de caja ahora se gestiona desde Caja y arqueo.', 'info')
    return redirect(url_for('cash_bp.register'))
