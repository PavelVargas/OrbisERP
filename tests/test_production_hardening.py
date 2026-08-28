from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_secrets_and_local_databases_are_ignored_and_sqlite_is_disabled():
    """A local installation legitimately has .env and may retain an old DB.

    What matters is that neither artifact can enter source control or become
    the configured database engine. Release packaging separately excludes both.
    """
    gitignore = (ROOT / '.gitignore').read_text(encoding='utf-8').splitlines()
    config_source = (ROOT / 'config.py').read_text(encoding='utf-8').lower()

    assert '.env' in gitignore
    assert '*.db' in gitignore
    assert 'sqlite://' not in config_source
    assert 'solo admite postgresql' in config_source


def test_exchange_rate_source_has_no_embedded_provider_key_or_fake_defaults():
    source = (ROOT / 'models/divisas/divisas.py').read_text(encoding='utf-8')
    assert 'fca_live_tu_clave_aqui' not in source
    assert 'FREECURRENCY_API_KEY' in source
    assert "'USD': 58.50" not in source


def test_cron_rejects_anonymous_requests_without_signed_secret():
    from app import app

    app.config.update(TESTING=True, CRON_SECRET='')
    response = app.test_client().post('/superadmin/cron/check-expirations', json={})
    assert response.status_code == 403


def test_every_private_application_route_has_permission_mapping():
    from app import app
    from permissions import required_permissions

    public = {
        'index', 'login_bp.login', 'login_bp.two_factor', 'login_bp.logout',
        'login_bp.forgot_password', 'registrar.register', 'registrar.verification_pending',
        'registrar.verify_email', 'registrar.resend_verification', 'users_bp.reset_with_token',
        'static', 'operations_bp.health_live', 'operations_bp.health_ready',
        'operations_bp.billing_webhook', 'superadmin_bp.cron_check_expirations',
    }
    missing = []
    for rule in app.url_map.iter_rules():
        endpoint = rule.endpoint
        if endpoint in public or endpoint.startswith(('static', 'superadmin_bp.', 'api_v1.')):
            continue
        methods = set(rule.methods) - {'HEAD', 'OPTIONS'}
        if not any(required_permissions(endpoint, method) for method in methods):
            missing.append((endpoint, rule.rule))
    assert not missing


def test_external_api_uses_api_key_authentication_and_scopes():
    source = (ROOT / 'routes/api_v1.py').read_text(encoding='utf-8')
    assert '@api_v1_bp.before_request' in source
    assert 'def authenticate_api_key' in source
    assert "auth.startswith('Bearer ')" in source
    assert 'g.api_company_id = api_key.company_id' in source
    for scope in ('products:read', 'inventory:read', 'clients:read', 'clients:write', 'sales:read'):
        assert f"_scope('{scope}')" in source


def test_production_compose_includes_persistent_backup_service():
    compose = (ROOT / 'docker-compose.production.yml').read_text(encoding='utf-8')
    assert 'backup:' in compose
    assert 'backups:/backups' in compose
    assert 'uploads:/uploads:ro' in compose


def test_sales_inputs_and_exchange_rates_are_tenant_safe():
    core = (ROOT / 'routes/sales/core.py').read_text(encoding='utf-8')
    login = (ROOT / 'routes/login/login.py').read_text(encoding='utf-8')
    cash = (ROOT / 'routes/cash/cash.py').read_text(encoding='utf-8')
    assert 'qty = product_quantity(' in core
    assert 'product=product' in core and 'uom=selected_uom' in core
    # POS mutations lock the active sale but use ``first()`` so AJAX callers
    # receive a detailed, tenant-safe JSON error instead of Flask's generic
    # HTML 404 page.
    assert "with_for_update().first()" in core
    assert 'La venta activa ya no existe' in core
    assert 'company_id=company_id' in core
    assert 'company_id=user.company_id' in login
    assert 'company_id=company_id' in cash


def test_plan_usage_counts_only_completed_sales():
    company = (ROOT / 'models/company/company.py').read_text(encoding='utf-8')
    assert "Sale.status == 'COMPLETED'" in company


def test_database_integrity_migration_is_present():
    migration = ROOT / 'migrations/versions/2a6e8c4b1d70_integrity_and_session_hardening.py'
    source = migration.read_text(encoding='utf-8')
    assert 'quantity > 0' in source
    assert 'quantity >= 0' in source
    assert 'session_version' in source
    assert 'trg_audit_logs_append_only' in source


def test_successful_mutations_are_audited():
    source = (ROOT / 'app.py').read_text(encoding='utf-8')
    assert 'def audit_successful_mutation' in source
    assert "request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}" in source


def test_mutations_use_persistent_idempotency_keys():
    security = (ROOT / 'security.py').read_text(encoding='utf-8')
    javascript = (ROOT / 'static/js/security.js').read_text(encoding='utf-8')
    operations = (ROOT / 'models/operations.py').read_text(encoding='utf-8')
    assert 'def _consume_idempotency_key' in security
    assert 'X-Idempotency-Key' in security
    assert '_idempotency_key' in security
    assert 'X-Idempotency-Key' in javascript
    assert 'class RequestIdempotency' in operations


def test_payment_receipts_use_private_authenticated_storage():
    company = (ROOT / 'routes/company/company.py').read_text(encoding='utf-8')
    superadmin = (ROOT / 'routes/super_admin/superadmin.py').read_text(encoding='utf-8')
    template = (ROOT / 'templates/superadmin/payments_management.html').read_text(encoding='utf-8')
    assert 'private=True' in company
    assert "@superadmin_required\ndef download_receipt" in superadmin
    assert 'superadmin_bp.download_receipt' in template
