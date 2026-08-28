from decimal import Decimal
from pathlib import Path

from services.money import as_decimal, exchange_rate, from_base, to_base

ROOT = Path(__file__).resolve().parents[1]


def test_money_helpers_never_mix_decimal_and_float():
    assert as_decimal(1.25) == Decimal('1.25')
    assert exchange_rate(0) == Decimal('1')
    assert from_base(Decimal('100.00'), 2.5) == Decimal('40.00')
    assert to_base(Decimal('40.00'), 2.5) == Decimal('100.00')


def test_client_360_keeps_postgresql_money_decimal_safe():
    source = (ROOT / 'routes/client/client.py').read_text(encoding='utf-8')
    assert 'conversion_rate = exchange_rate(' in source
    assert 'float(exchange.rate' not in source
    assert 'as_decimal(sale.balance)' in source


def test_release_schema_adds_email_verification_without_locking_existing_users():
    migration = (ROOT / 'migrations/versions/6f7b2d4c9a11_release_readiness.py').read_text(encoding='utf-8')
    assert "revision = '6f7b2d4c9a11'" in migration
    assert "down_revision = '5d2a8c91e740'" in migration
    assert 'UPDATE users SET email_verified_at = NOW()' in migration


def test_production_requires_verified_public_accounts():
    config = (ROOT / 'config.py').read_text(encoding='utf-8')
    registration = (ROOT / 'routes/registro/registro.py').read_text(encoding='utf-8')
    login = (ROOT / 'routes/login/login.py').read_text(encoding='utf-8')
    assert 'REQUIRE_EMAIL_VERIFICATION' in config
    assert '_send_verification_email' in registration
    assert 'user.email_verified' in login


def test_csp_uses_nonces_for_script_and_style_blocks():
    source = (ROOT / 'security.py').read_text(encoding='utf-8')
    assert "script-src 'self' 'nonce-" in source
    assert "style-src 'self' 'nonce-" in source
    assert "script-src 'self' 'unsafe-inline'" not in source
    assert "style-src 'self' 'unsafe-inline'" not in source


def test_release_builder_excludes_runtime_and_secret_material():
    source = (ROOT / 'scripts/build_release.py').read_text(encoding='utf-8')
    assert "'.git'" in source
    assert "'.env'" in source
    assert "'.auditvenv'" in source
    assert "'AUDIT_VERIFIED_20260827.md'" in source
    assert "'POS_UI_VALIDATION.json'" in source
    assert "Path('static/uploads')" in source
    assert "'__pycache__'" in source


def test_public_registration_has_explicit_legal_gate():
    config = (ROOT / 'config.py').read_text(encoding='utf-8')
    route = (ROOT / 'routes/registro/registro.py').read_text(encoding='utf-8')
    template = (ROOT / 'templates/registro/register.html').read_text(encoding='utf-8')
    assert 'PUBLIC_REGISTRATION' in config
    assert 'TERMS_URL' in config and 'PRIVACY_URL' in config and 'LEGAL_VERSION' in config
    assert "request.form.get('accept_terms')" in route
    assert 'terms_accepted_at=utcnow()' in route
    assert 'name="accept_terms"' in template


def test_password_policy_accepts_long_passphrases_and_rejects_weak_values():
    from security import password_error
    assert password_error('short') is not None
    assert password_error('password1234') is not None
    assert password_error('CorrectHorseBatteryStaple') is None
    assert password_error('StrongPass2026') is None


def test_500_incident_webhook_never_contains_request_body():
    source = (ROOT / 'app.py').read_text(encoding='utf-8')
    assert '_dispatch_error_webhook' in source
    assert "'event': 'http.500'" in source
    webhook_block = source.split("'event': 'http.500'", 1)[1].split('})', 1)[0]
    assert 'request.form' not in webhook_block
    assert 'request.get_json' not in webhook_block


def test_production_email_links_use_trusted_public_base_url():
    config = (ROOT / 'config.py').read_text(encoding='utf-8')
    registration = (ROOT / 'routes/registro/registro.py').read_text(encoding='utf-8')
    login = (ROOT / 'routes/login/login.py').read_text(encoding='utf-8')
    assert 'PUBLIC_BASE_URL' in config
    assert "PUBLIC_BASE_URL.startswith('https://')" in config
    assert "current_app.config.get('PUBLIC_BASE_URL')" in registration
    assert "current_app.config.get('PUBLIC_BASE_URL')" in login


def test_error_webhook_is_https_and_signed_in_production():
    config = (ROOT / 'config.py').read_text(encoding='utf-8')
    assert "ERROR_WEBHOOK_URL.startswith('https://')" in config
    assert 'ERROR_WEBHOOK_SECRET debe tener al menos 32 caracteres' in config


def test_login_hides_self_signup_when_public_registration_is_disabled():
    template = (ROOT / 'templates/login/login.html').read_text(encoding='utf-8')
    assert "config.get('PUBLIC_REGISTRATION')" in template
    assert "url_for('registrar.register')" in template


def test_ci_runs_postgresql_http_and_browser_smoke_tests():
    workflow = (ROOT / '.github/workflows/quality.yml').read_text(encoding='utf-8')
    assert 'requirements-dev.txt' in workflow
    assert 'playwright install --with-deps chromium' in workflow
    assert 'tests/e2e' in workflow
    assert 'TEST_DATABASE_URL' in workflow


def test_production_rejects_flask_debug_mode():
    config = (ROOT / 'config.py').read_text(encoding='utf-8')
    assert "os.getenv('FLASK_DEBUG', '0') == '1'" in config
    assert 'no pueden estar activos en producción' in config


def test_production_container_runs_hardened_and_non_root():
    dockerfile = (ROOT / 'Dockerfile').read_text(encoding='utf-8')
    compose = (ROOT / 'docker-compose.production.yml').read_text(encoding='utf-8')
    assert 'USER orbiserp' in dockerfile
    assert 'read_only: true' in compose
    assert 'no-new-privileges:true' in compose
    assert 'cap_drop:' in compose and '- ALL' in compose


def test_private_documents_validate_content_not_browser_mime():
    from services.file_validation import validate_document_bytes
    assert validate_document_bytes(b'%PDF-1.7\n%%EOF', 'pdf') == 'application/pdf'
    with __import__('pytest').raises(ValueError):
        validate_document_bytes(b'<script>alert(1)</script>', 'pdf')
    source = (ROOT / 'routes/workspace.py').read_text(encoding='utf-8')
    assert 'validate_document_bytes(content, extension)' in source
    assert "mime_type=canonical_mime" in source


def test_admin_password_reset_links_also_use_public_base_url():
    source = (ROOT / 'routes/users/users.py').read_text(encoding='utf-8')
    assert "current_app.config.get('PUBLIC_BASE_URL')" in source
    assert "reset_path = url_for('users_bp.reset_with_token'" in source


def test_release_builder_uses_clean_brand_root_and_reproducible_metadata():
    source = (ROOT / 'scripts/build_release.py').read_text(encoding='utf-8')
    assert "default='OrbisERP'" in source
    assert 'FIXED_ZIP_TIME' in source
    assert "Path('static/uploads')" in source


def test_production_requires_encrypted_smtp_transport():
    config = (ROOT / 'config.py').read_text(encoding='utf-8')
    assert 'MAIL_USE_TLS=1 es obligatorio' in config


def test_release_version_is_file_backed_and_exposed_operationally():
    import re
    version = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
    assert re.fullmatch(r'\d{4}\.\d{2}\.\d+', version)
    config = (ROOT / 'config.py').read_text(encoding='utf-8')
    operations = (ROOT / 'routes/operations.py').read_text(encoding='utf-8')
    assert "BASE_DIR / 'VERSION'" in config
    assert "release=current_app.config.get('RELEASE_VERSION')" in operations



def test_release_identity_has_single_source_of_truth():
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, str(ROOT / 'scripts/release_identity.py')],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert 'OK release=' in result.stdout and 'alembic_head=' in result.stdout


def test_expected_schema_revision_is_derived_from_alembic_graph():
    config = (ROOT / 'config.py').read_text(encoding='utf-8')
    helper = (ROOT / 'schema_identity.py').read_text(encoding='utf-8')
    assert 'from schema_identity import discover_alembic_head' in config
    assert 'EXPECTED_SCHEMA_REVISION = discover_alembic_head(BASE_DIR)' in config
    assert 'discover_alembic_head' in helper


def test_ci_audits_python_dependencies():
    workflow = (ROOT / '.github/workflows/quality.yml').read_text(encoding='utf-8')
    requirements = (ROOT / 'requirements-dev.txt').read_text(encoding='utf-8')
    assert 'pip-audit' in requirements
    assert 'pip-audit -r requirements.txt' in workflow
    assert 'python -m pip check' in workflow


def test_official_production_deployment_requires_trusted_single_proxy():
    config = (ROOT / 'config.py').read_text(encoding='utf-8')
    assert 'TRUST_PROXY=1 es obligatorio' in config
    app = (ROOT / 'app.py').read_text(encoding='utf-8')
    assert 'ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)' in app


def test_runtime_refuses_stale_schema_before_superadmin_query():
    source = (ROOT / 'app.py').read_text(encoding='utf-8')
    startup = source.split("if app.config['AUTO_CREATE_SCHEMA']", 1)[1].split('# =========================\n# REGISTER BLUEPRINTS', 1)[0]
    assert 'require_current_schema()' in startup
    assert startup.index('require_current_schema()') < startup.index('create_superadmin()')
    assert 'db.create_all()' not in startup
    assert 'flask --app app db upgrade' in source


def test_superadmin_bootstrap_rolls_back_and_propagates_database_errors():
    source = (ROOT / 'app.py').read_text(encoding='utf-8')
    block = source.split('def create_superadmin():', 1)[1].split("@app.cli.command('create-superadmin')", 1)[0]
    assert 'db.session.rollback()' in block
    assert 'raise' in block
    assert 'Error creando superadmin' not in block
