from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(path):
    return (ROOT / path).read_text(encoding='utf-8')


def test_superadmin_has_companyless_master_sections():
    routes = source('routes/super_admin/superadmin.py')
    assert "@superadmin_bp.get('/superadmin/clients')" in routes
    assert "@superadmin_bp.get('/superadmin/activity')" in routes
    assert "@superadmin_bp.route('/superadmin/payments')" in routes
    assert "def _clear_tenant_context():" in routes
    assert "'company_id'" in routes
    assert "Company.query.order_by" in routes


def test_support_impersonation_context_is_preserved_by_global_session_sync():
    app = source('app.py')
    assert "support_context = bool(" in app
    assert "authenticated_user.role == 'superadmin'" in app
    assert "and session.get('impersonating')" in app
    assert "if not support_context:" in app


def test_manual_payment_approval_creates_billing_history():
    routes = source('routes/super_admin/superadmin.py')
    block = routes.split('def approve_payment(id):', 1)[1].split("@superadmin_bp.route('/superadmin/renew_plan", 1)[0]
    assert 'with_for_update()' in block
    assert 'BillingInvoice(' in block
    assert "provider='manual_receipt'" in block
    assert "status='PAID'" in block
    assert 'paid_at=now' in block


def test_superadmin_uses_same_compact_odoo_dark_language():
    css = source('static/css/superadmin_css/superadmin.css')
    base = source('templates/superadmin/base.html')
    assert '#191b1f' in css
    assert '#222428' in css
    assert "css/orbis_refined.css" in base
    assert "css/orbis_compact.css" in base
    assert 'sa-sidebar' in base
    assert 'Sin empresa asignada' in base
