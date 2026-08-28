import json
import re
from pathlib import Path
from types import SimpleNamespace

from flask import Flask

from permissions import required_permissions
from security import consume_recovery_code, generate_recovery_codes, hash_session_token, store_recovery_codes


ROOT = Path(__file__).resolve().parents[1]


def test_recovery_codes_are_unique_hashed_and_single_use():
    app = Flask(__name__)
    app.secret_key = 'test-secret-that-is-long-enough'
    user = SimpleNamespace(totp_recovery_codes=None)
    with app.app_context():
        codes = generate_recovery_codes(8)
        assert len(codes) == len(set(codes)) == 8
        store_recovery_codes(user, codes)
        assert codes[0].replace('-', '') not in user.totp_recovery_codes
        assert len(json.loads(user.totp_recovery_codes)) == 8
        assert consume_recovery_code(user, codes[0].lower()) is True
        assert consume_recovery_code(user, codes[0]) is False
        assert len(json.loads(user.totp_recovery_codes)) == 7


def test_session_tokens_are_not_stored_in_plaintext():
    token = 'private-session-token'
    digest = hash_session_token(token)
    assert token not in digest
    assert len(digest) == 64
    assert digest == hash_session_token(token)


def test_governance_endpoints_have_specific_permissions():
    assert required_permissions('governance_bp.integrity_center', 'GET') == ('operations.integrity',)
    assert required_permissions('governance_bp.audit_export', 'GET') == ('audits.export',)
    assert required_permissions('governance_bp.revoke_session', 'POST') == ('sessions.manage',)


def test_governance_migration_is_the_configured_head():
    migration = ROOT / 'migrations/versions/4c9e2f7a6b10_productivity_suite.py'
    source = migration.read_text(encoding='utf-8')
    assert "revision = '4c9e2f7a6b10'" in source
    assert "down_revision = '3b7f9d5c2e81'" in source
    assert 'cash_sessions' in source
    assert 'notification_rules' in source
    assert 'sales_taxes' in source


def test_governance_templates_compile():
    from app import app

    for name in (
        'governance/integrity.html', 'governance/audit.html', 'governance/system.html',
        'governance/processes.html', 'governance/sessions.html',
    ):
        app.jinja_env.get_template(name)


def test_literal_template_endpoints_exist():
    """Catch misspelled url_for endpoints before a page reaches production."""
    from app import app

    known = {rule.endpoint for rule in app.url_map.iter_rules()}
    referenced = set()
    for template in (ROOT / 'templates').rglob('*.html'):
        source = template.read_text(encoding='utf-8')
        referenced.update(re.findall(r"url_for\(\s*['\"]([^'\"]+)['\"]", source))
    assert not sorted(referenced - known)
