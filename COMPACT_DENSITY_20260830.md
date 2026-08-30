# OrbisERP Compact Density · 2026-08-30

Global desktop density pass requested after visual QA.

## Goal
Fit materially more business information in each viewport without using browser zoom or scaling the application canvas.

## Changes
- Desktop sidebar: 232 px -> 210 px.
- Desktop topbar: 60 px -> 50 px.
- Main page top/bottom whitespace reduced.
- Page headings, descriptions and action rows reduced proportionally.
- Cards/panels use 13 px internal padding instead of 20 px where the shared system applies.
- KPI cards reduced from ~116 px to ~82 px minimum height.
- Form controls reduced to ~34 px on desktop.
- Table cell padding reduced from 12x14 px to 7x9 px.
- List rows, badges, tabs and empty states compacted.
- CRM workbench, purchase order editor and scanner receive dedicated density rules.
- POS remains image-led while fitting more products and checkout controls in one viewport.
- Tablet/mobile preserve touch-friendly sizing and only reduce excessive outer whitespace.

## Implementation
`static/css/orbis_compact.css` is intentionally loaded last in complete templates so historical module CSS cannot re-expand the interface.
