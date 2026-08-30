# OrbisERP · Smooth Navigation Fix · 2026-08-29

- Removed the route-cover overlay that appeared immediately on link clicks/forms and made navigation feel blocked.
- Kept server-seeded dark/light canvas, so zero-flash behavior does not depend on the overlay.
- Reduced full-view entrance motion from 500 ms / 8 px to 145 ms / 3 px.
- Removed repeated sidebar and POS topbar entrance animations.
- Reduced general micro-interactions to 120 ms.
- Reduced modal/popover animation durations while preserving visual feedback.
- Kept document-level theme transitions disabled to prevent light/dark flashes.
- Asset version bumped to `20260829-smooth1` to bypass stale browser cache.

- Reduced legacy `.orbis-page` motion from 420 ms to 140 ms and reveal motion from 500 ms to 160 ms.
- Removed the tablet navigation's artificial 105 ms delay and card stagger.
