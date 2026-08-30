# Odoo 19-inspired dark mode + transfer continuous lines · 2026-08-30

## Dark mode
- Replaced the previous near-black palette with a graphite hierarchy inspired by Odoo 19 backend themes.
- Canonical dark canvas: `#191b1f`.
- Main surfaces: `#222428`; secondary surfaces: `#282b30`; hover: `#30343a`.
- Subtle separators: `#34373d` / `#484c55`.
- OrbisERP keeps orange as its product brand/action color (`#ff7a45` in dark mode).
- First-paint theme bootstrap, runtime theme sync, sidebar fallback and POS now share the same dark canvas so navigation does not flash between two dark palettes.

## Transfers
- New transfer creation now follows the same continuous-line interaction used by purchase orders.
- No “Agregar producto” button or add-product card.
- Permanent blank line: product -> Enter -> quantity -> Enter -> next line.
- Product suggestions float above the table and remain keyboard navigable.
- Duplicate product lines are allowed in the editor.
- Availability validation aggregates duplicate lines before checking stock, matching backend safety rules.
- Sidebar remains unchanged.
