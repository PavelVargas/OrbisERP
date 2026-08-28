# OrbisERP 2026.08.13

ERP/POS web multiempresa para retail y distribución: ventas, compras, caja, CRM, cartera, documentos, auditoría, inventario multi-almacén y capacidades Retail 2.0 configurables por empresa.

## Retail 2.0

Incluye sucursales/terminales, variantes, UOM y conversiones por producto, códigos de barras múltiples, listas de precios, lotes/FEFO, seriales/IMEI, garantías, kits, crédito, apartados, gift cards, fidelización, pagos mixtos, calidad de devoluciones, reposición, costeo, API v1 y webhooks. Consulta `RETAIL_PLATFORM.md`.

## Desarrollo

1. Copia `.env.example` a `.env` y configura PostgreSQL.
2. `python -m venv .venv && source .venv/bin/activate`
3. `pip install -r requirements-dev.txt`
4. `flask --app app db upgrade`
5. `python app.py`

## QA

La auditoría estática no necesita Flask ni PostgreSQL:

```bash
python scripts/static_release_audit.py
```

La certificación dinámica requiere una base PostgreSQL **exclusiva de pruebas**:

```bash
export TEST_DATABASE_URL='postgresql+psycopg://.../orbiserp_test'
pytest -q -rs --ignore=tests/e2e
```

El CI ejecuta además Playwright/Chromium contra PostgreSQL real.

## Producción

Lee `PRODUCTION.md`, `MAINTENANCE.md`, `COMMERCIAL_RELEASE.md`, `RETAIL_PLATFORM.md` y `RELEASE_CHECKLIST.md`. No distribuyas el workspace: genera el ZIP limpio con `scripts/build_release.py`.


> Desde 2026.08.13 el arranque valida el head Alembic antes de consultar modelos. Si la base está atrasada, ejecuta `flask --app app db upgrade`; el servidor no continuará con un esquema parcial.
