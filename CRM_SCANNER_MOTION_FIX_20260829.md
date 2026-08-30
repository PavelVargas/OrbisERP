# CRM + Scanner + Motion stability · 2026-08-29

## CRM
- Rebuilt `static/css/crm_polished.css` as the CRM visual authority.
- Stable master/detail layout, consistent orange/system tokens, dark mode and responsive drawer.
- Removed card/section lift effects.
- Hardened `static/js/crm/crm.js` with CSRF/idempotency headers, AbortController cancellation, safer error handling, local-date task defaults and duplicate-status protection.
- Preserved all existing CRM DOM ids, endpoints and business actions.

## Transfer scanner
- Rebuilt `static/css/scanner.css` to match the authenticated application shell.
- Scanner CSS now loads after `orbis_refined.css` so its workstation-specific layout is deterministic.
- Uses the same orange, surface, spacing, radius and dark-mode tokens as the rest of OrbisERP.
- Removed workstation shake/bump animation while keeping scan/audio/vibration feedback and all scanner hooks intact.

## Motion
- Removed the IntersectionObserver reveal layer from `static/js/commercial.js`.
- Removed page-entry transforms, card lift, press scaling and section bounce in the final UI authority.
- Kept fast color/focus feedback (90ms) and independent overlay/modal motion.
- Bumped the shared asset version to `20260829-smooth2` to avoid stale browser cache.

## Validation
- Node syntax: CRM/commercial/scanner JS OK.
- CSS parsing: CRM/scanner/refined/commercial 0 parse errors.
- Jinja: 118 templates parsed.
- Static release audit: OK.
- UI consistency audit: OK.
- Client UI audit: OK.
- Static scanner/dark/system/tablet contracts: 20 passed.
