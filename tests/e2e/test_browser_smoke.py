import os

import pytest

playwright = pytest.importorskip('playwright.sync_api')
from playwright.sync_api import expect

BASE_URL = os.getenv('E2E_BASE_URL')
pytestmark = pytest.mark.skipif(not BASE_URL, reason='E2E_BASE_URL no configurado')


def test_browser_login_and_critical_screens():
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        response = page.goto(f'{BASE_URL}/login', wait_until='networkidle')
        assert response and response.status == 200
        page.locator('input[name="email"]').fill('e2e.admin@orbiserp.test')
        page.locator('input[name="password"]').fill('E2E-Release-2026-Strong')
        page.locator('form').locator('button[type="submit"]').click()
        page.wait_for_load_state('networkidle')
        assert '/dashboard' in page.url
        expect(page.locator('body')).not_to_contain_text('Algo no salió como esperábamos')

        for path in ['/dashboard', '/list_product', '/clients/', '/crm', '/sales/', '/warehouses/', '/governance/audit', '/retail/', '/retail/warranties', '/retail/quality', '/reports/retail-performance']:
            response = page.goto(f'{BASE_URL}{path}', wait_until='networkidle')
            assert response and response.status == 200, path
            expect(page.locator('body')).not_to_contain_text('Algo no salió como esperábamos')

        # Cliente 360 specifically exercises the screen that previously raised 500s.
        # Resolve the seeded client from PostgreSQL instead of relying on a fragile UI selector
        # that could accidentally click /clients/create.
        from app import app
        from models.client.client import Client
        with app.app_context():
            seeded_client = Client.query.filter_by(name='Cliente E2E').first()
            assert seeded_client is not None
            client_id = seeded_client.id
        response = page.goto(f'{BASE_URL}/clients/{client_id}', wait_until='networkidle')
        assert response and response.status == 200
        expect(page.locator('body')).not_to_contain_text('Algo no salió como esperábamos')
        browser.close()
