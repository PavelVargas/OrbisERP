# Superadmin platform workspace — 2026-08-30

- Superadmin works in a master context without `company_id`.
- Tenant impersonation is explicit and the selected company context is preserved only while support mode is active.
- New canonical sections: Resumen, Clientes, Pagos, Actividad.
- The master UI now uses the same compact density, orange brand and Odoo-19-inspired graphite dark mode as the rest of OrbisERP.
- Manual receipt approvals create a `BillingInvoice` record so platform payments have durable history.
- Payment history includes customer/company, plan, amount, currency, provider, reference, paid date and period end.
- Administrative renewals do not silently count as revenue.
- The legacy `/list-companies` superadmin view redirects to the canonical master Clients section.
