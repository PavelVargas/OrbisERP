import time

from security import _totp_at, generate_totp_secret, verify_totp


def test_totp_round_trip_and_rejects_invalid_codes():
    secret = generate_totp_secret()
    code = _totp_at(secret, int(time.time()) // 30)
    assert len(secret) >= 24
    assert verify_totp(secret, code)
    assert not verify_totp(secret, '12345')


def test_backoffice_routes_are_registered():
    from app import app
    endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}
    expected = {
        'backoffice_bp.overview', 'backoffice_bp.returns', 'backoffice_bp.create_return',
        'backoffice_bp.receivables', 'backoffice_bp.receive_payment',
        'backoffice_bp.payables', 'backoffice_bp.pay_supplier', 'backoffice_bp.expenses',
        'backoffice_bp.inventory_counts', 'backoffice_bp.inventory_count_detail',
        'backoffice_bp.approve_inventory_count', 'backoffice_bp.notifications',
        'backoffice_bp.security_settings', 'login_bp.two_factor',
    }
    assert expected <= endpoints
