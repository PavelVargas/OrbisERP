# OrbisERP 2026.08.13 — condición de release comercial

## Alcance que sí puede comercializarse

OrbisERP puede venderse como ERP web/POS para retail y distribución con gestión comercial, inventario multi-almacén, ventas, cotizaciones, compras, caja, CRM, clientes, proveedores, CxC/CxP, documentos, auditoría y capacidades Retail 2.0: sucursales/terminales, variantes, UOM, pricing, lotes, seriales, garantías, kits, crédito, apartados, gift cards, fidelización y API/webhooks.

## Límites que deben comunicarse al cliente

- `FISCAL_MODE=disabled`: los documentos son comerciales/no fiscales hasta integrar un proveedor fiscal autorizado para el país del cliente.
- `BILLING_MODE=manual` no es cobro SaaS automático. Usa `webhook` únicamente al integrar una pasarela real.
- La aplicación Electron es un cliente de escritorio; distribución firmada/autoactualización requiere certificados y pipeline de cada plataforma.
- Las plantillas legales del repositorio no equivalen a revisión jurídica. El registro público en producción exige URLs externas de Términos y Privacidad y una `LEGAL_VERSION` publicada.

## Gates automáticos añadidos

Producción falla al arrancar si:

- la `SECRET_KEY` es débil;
- cookies seguras están desactivadas;
- el esquema intenta autocrearse;
- rate limiting no usa PostgreSQL;
- SMTP no está configurado;
- verificación de email está desactivada;
- el registro público está activo sin Términos/Privacidad HTTPS y versión legal;
- el modo webhook no tiene secreto suficiente.

## QA de release

CI ejecuta PostgreSQL real, migraciones, auditoría de integridad, validación de constraints, tests unitarios/contrato y smoke tests HTTP que renderizan las pantallas críticas con datos `Decimal` reales.

Antes de entregar a un cliente, ejecuta primero `python scripts/static_release_audit.py`. La certificación dinámica debe usar `TEST_DATABASE_URL` exclusivo de pruebas.

```bash
flask --app app db upgrade
flask --app app audit-integrity
flask --app app validate-integrity
pytest -q -rs --ignore=tests/e2e
python scripts/build_release.py --output dist/OrbisERP_2026.08.13_commercial.zip
```

## Requisitos externos antes de General Availability

1. revisión legal/privacidad por profesional competente;
2. política de soporte/SLA y tratamiento de incidentes;
3. backup off-site real y simulacro mensual de restauración;
4. monitorización externa de uptime/5xx/recursos;
5. TLS y dominio de producción;
6. prueba de penetración independiente antes de clientes de alto riesgo;
7. integración fiscal certificada si se vende como facturación fiscal.

## QA de navegador y regresión

El pipeline de calidad también instala Chromium mediante Playwright, crea datos de prueba aislados, inicia OrbisERP contra PostgreSQL y recorre en un navegador real Login, Dashboard, Productos, Clientes/Cliente 360, CRM, Ventas, Almacenes y Auditoría. Esto complementa los tests HTTP y evita certificar un release únicamente porque el código compile.

La publicación debe bloquearse si falla cualquiera de estas capas:

1. migración PostgreSQL;
2. auditoría/constraints;
3. tests unitarios y HTTP;
4. smoke E2E de navegador;
5. build y verificación del ZIP limpio.


## Retail 2.0

El modelo operativo Retail 2.0 y sus límites están documentados en `RETAIL_PLATFORM.md`. La activación de una capacidad no sustituye la configuración del negocio: UOM, reglas de precio, lotes, seriales, crédito, terminales y políticas deben parametrizarse antes de operar con datos reales.
