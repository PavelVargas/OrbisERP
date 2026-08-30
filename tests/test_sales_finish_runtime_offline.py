"""Execute the exact POS finish functions without importing Flask.

This regression test compiles the production AST and supplies small fakes for
Flask and SQLAlchemy collaborators. It verifies the cashier-critical contract:
a cash/card/transfer sale can be finalized for ``Consumidor final`` and the UI
must not report a failure after the database transaction has committed.
"""
from __future__ import annotations

import ast
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


class BusinessRuleError(ValueError):
    pass


class FakeQuery:
    def __init__(self, result=None):
        self.result = result
        self.filters = {}
        self.locked = False

    def filter_by(self, **kwargs):
        self.filters = kwargs
        return self

    def with_for_update(self):
        self.locked = True
        return self

    def first(self):
        return self.result


class FakeModel:
    query = FakeQuery()


class Company(FakeModel):
    pass


class Sale(FakeModel):
    pass


class User(FakeModel):
    pass


class GiftCard(FakeModel):
    pass


class SalePayment:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class FakeSession:
    def __init__(self):
        self.added = []
        self.commit_count = 0
        self.rollback_count = 0

    def add(self, row):
        self.added.append(row)

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1


class FakeLogger:
    def __init__(self):
        self.exceptions = []

    def exception(self, message, *args):
        self.exceptions.append(message % args if args else message)


class FakeBlueprint:
    def route(self, *_args, **_kwargs):
        return lambda function: function


def as_decimal(value):
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or 0))


def compile_finish(*, payment_method='CASH', sale_status='PENDING', has_items=True, webhook_fails=False, cash_received=None):
    source = (ROOT / 'routes/sales/actions.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    names = {'_money', '_payment_plan', 'finish_sale'}
    functions = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    module = ast.Module(body=functions, type_ignores=[])
    ast.fix_missing_locations(module)

    item = SimpleNamespace(id=1, warehouse_id=3)
    sale = SimpleNamespace(
        id=1842,
        company_id=2,
        user_id=7,
        status=sale_status,
        items=[item] if has_items else [],
        total=Decimal('739.50'),
        subtotal=Decimal('739.50'),
        itbis=Decimal('0.00'),
        discount_amount=Decimal('0.00'),
        client=None,
        client_id=None,
        customer_name=None,
        terminal_id=None,
        branch_id=1,
        payment_method=None,
        amount_paid=Decimal('0.00'),
        balance=Decimal('0.00'),
        created_at=None,
    )
    company = SimpleNamespace(
        id=2,
        get_plan_limits=lambda: {'max_monthly_invoices': 5000},
        get_current_month_usage=lambda: 12,
    )
    user = SimpleNamespace(id=7, company_id=2, warehouse_id=None)
    Company.query = FakeQuery(company)
    Sale.query = FakeQuery(sale)
    User.query = FakeQuery(user)
    GiftCard.query = FakeQuery(None)

    orm_session = FakeSession()
    browser_session = {'company_id': 2, 'current_sale_id': 1842, 'user_id': 7}
    form = {'payment_method': payment_method}
    if cash_received is not None:
        form['cash_received'] = str(cash_received)
    request = SimpleNamespace(
        headers={'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'},
        form=form,
    )
    logger = FakeLogger()
    calls = {
        'reserved': [],
        'finalized': [],
        'events': [],
        'loyalty': [],
        'flashes': [],
    }

    def ensure_credit_allowed(client, amount):
        if client is None:
            raise BusinessRuleError('Selecciona un cliente para vender a crédito.')

    def emit_event(company_id, event_name, payload):
        calls['events'].append((company_id, event_name, payload))
        if webhook_fails:
            raise RuntimeError('fixture webhook unavailable')

    def url_for(endpoint, **values):
        mapping = {
            'sales_bp.create_sale': '/sales/create',
            'sales_bp.list_sales': '/sales/',
            'login_bp.login': '/login',
            'login_bp.logout': '/logout',
        }
        if endpoint == 'sales_bp.sale_detail':
            return f"/sales/{values['sale_id']}"
        return mapping.get(endpoint, f'/{endpoint}')

    namespace = {
        'Decimal': Decimal,
        'BusinessRuleError': BusinessRuleError,
        'request': request,
        'session': browser_session,
        'flash': lambda message, category='message': calls['flashes'].append((category, message)),
        'redirect': lambda destination: {'redirect': destination},
        'url_for': url_for,
        'current_app': SimpleNamespace(logger=logger),
        'jsonify': lambda **payload: payload,
        'g': SimpleNamespace(request_id='offline-finish-1842'),
        'db': SimpleNamespace(session=orm_session),
        'Sale': Sale,
        'Company': Company,
        'User': User,
        'SalePayment': SalePayment,
        'GiftCard': GiftCard,
        'utcnow': lambda: datetime(2026, 8, 27, tzinfo=timezone.utc),
        'as_decimal': as_decimal,
        'ensure_credit_allowed': ensure_credit_allowed,
        'get_retail_settings': lambda company_id, create=False: SimpleNamespace(),
        'reserve_serials_for_item': lambda current: calls['reserved'].append(current.id),
        'loyalty_redemption_quote': lambda *_args, **_kwargs: (Decimal('0'), Decimal('0')),
        'redeem_loyalty': lambda *args: calls['loyalty'].append(args),
        'finalize_sale_inventory_and_loyalty': lambda current, settings=None: calls['finalized'].append(current.id),
        'emit_event': emit_event,
        'recalc_sale': lambda current: None,
        'resolve_sale_warehouse': lambda *_args, **_kwargs: None,
        'sales_bp': FakeBlueprint(),
    }
    exec(compile(module, str(ROOT / 'routes/sales/actions.py'), 'exec'), namespace)
    return namespace['finish_sale'], sale, browser_session, orm_session, calls, logger


def test_consumer_final_sale_commits_for_cash_card_and_transfer():
    for method in ('CASH', 'CARD', 'TRANSFER'):
        finish, sale, browser_session, orm_session, calls, logger = compile_finish(payment_method=method)

        response = finish()

        assert response == {
            'ok': True,
            'message': 'Venta #1842 finalizada exitosamente.',
            'redirect': '/sales/1842',
            'sale_id': 1842,
        }
        assert sale.status == 'COMPLETED'
        assert sale.customer_name == 'Consumidor final'
        assert sale.payment_method == method
        assert sale.amount_paid == Decimal('739.50')
        assert sale.balance == Decimal('0.00')
        if method == 'CASH':
            assert sale.cash_received == Decimal('739.50')
            assert sale.cash_change == Decimal('0.00')
        else:
            assert sale.cash_received is None
            assert sale.cash_change == Decimal('0.00')
        assert browser_session.get('current_sale_id') is None
        assert orm_session.commit_count == 1
        assert orm_session.rollback_count == 0
        assert calls['reserved'] == [1]
        assert calls['finalized'] == [1842]
        assert len(orm_session.added) == 1
        payment = orm_session.added[0]
        assert payment.method == method
        assert payment.amount == Decimal('739.50')
        assert calls['events'][0][1] == 'sale.completed'
        assert logger.exceptions == []


def test_post_commit_webhook_failure_still_reports_the_sale_as_completed():
    finish, sale, browser_session, orm_session, calls, logger = compile_finish(webhook_fails=True)

    response = finish()

    assert response['ok'] is True
    assert sale.status == 'COMPLETED'
    assert browser_session.get('current_sale_id') is None
    assert orm_session.commit_count == 1
    assert orm_session.rollback_count == 0
    assert logger.exceptions and 'after commit' in logger.exceptions[0]


def test_credit_sale_without_client_is_rejected_before_commit():
    finish, sale, browser_session, orm_session, calls, _logger = compile_finish(payment_method='CREDIT')

    payload, status = finish()

    assert status == 409
    assert payload['ok'] is False
    assert 'cliente' in payload['error'].lower()
    assert sale.status == 'PENDING'
    assert browser_session['current_sale_id'] == 1842
    assert orm_session.commit_count == 0
    assert orm_session.rollback_count == 1
    assert calls['finalized'] == []
    assert orm_session.added == []


def test_empty_order_cannot_be_finalized():
    finish, sale, browser_session, orm_session, calls, _logger = compile_finish(has_items=False)

    payload, status = finish()

    assert status == 409
    assert payload['ok'] is False
    assert 'al menos un producto' in payload['error']
    assert sale.status == 'PENDING'
    assert browser_session['current_sale_id'] == 1842
    assert orm_session.commit_count == 0
    assert orm_session.rollback_count == 0
    assert calls['finalized'] == []


def test_repeated_request_after_completion_is_idempotent():
    finish, sale, browser_session, orm_session, calls, _logger = compile_finish(sale_status='COMPLETED')

    response = finish()

    assert response['ok'] is True
    assert response['message'] == 'La venta ya había sido finalizada.'
    assert response['sale_id'] == 1842
    assert browser_session.get('current_sale_id') is None
    assert orm_session.commit_count == 0
    assert orm_session.added == []
    assert calls['finalized'] == []

def test_cash_sale_persists_tendered_amount_and_change():
    finish, sale, browser_session, orm_session, calls, logger = compile_finish(
        payment_method='CASH', cash_received='800.00'
    )

    response = finish()

    assert response['ok'] is True
    assert sale.status == 'COMPLETED'
    assert sale.amount_paid == Decimal('739.50')
    assert sale.cash_received == Decimal('800.00')
    assert sale.cash_change == Decimal('60.50')
    assert orm_session.commit_count == 1
    assert orm_session.rollback_count == 0


def test_cash_sale_rejects_tender_below_amount_due():
    finish, sale, browser_session, orm_session, calls, logger = compile_finish(
        payment_method='CASH', cash_received='700.00'
    )

    payload, status = finish()

    assert status == 409
    assert payload['ok'] is False
    assert 'efectivo recibido' in payload['error'].lower()
    assert sale.status == 'PENDING'
    assert orm_session.commit_count == 0
    assert orm_session.rollback_count == 1

