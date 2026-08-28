from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_registration_uses_four_digit_email_code():
    route = (ROOT / 'routes/registro/registro.py').read_text(encoding='utf-8')
    assert "secrets.randbelow(10000)" in route
    assert "len(code) == 4" in route
    assert "hmac.compare_digest" in route
    assert "email_verification_code_expires_at" in route
    assert "message.html" in route


def test_company_registration_reuses_logged_in_owner():
    template = (ROOT / 'templates/company/create_company.html').read_text(encoding='utf-8')
    route = (ROOT / 'routes/company/company.py').read_text(encoding='utf-8')
    assert 'name="admin_email"' not in template
    assert 'name="password"' not in template
    assert 'Propietario de la empresa' in template
    assert "user.company_id = new_company.id" in route
    assert "company_email" in route
    assert "request.files.get('logo')" in route
