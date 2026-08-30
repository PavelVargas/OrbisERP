# Dark mode zero-flash fix · 2026-08-29

The previous implementation still allowed the browser's default document canvas
to become visible for one frame during a full document navigation.

This revision fixes the problem at four levels:

1. `meta[name=color-scheme]` and `theme-color` are server-seeded before external CSS.
2. The server seed is a canonical dark-mode selector in `orbis_refined.css`.
3. Full-page internal navigation paints a theme-matched route shield before commit.
4. Page/tablet entrance motion no longer fades the whole page from/to transparent.

The theme cookie remains the cross-request source used for first paint, while
localStorage is reconciled immediately and kept synchronized by `theme-sync.js`.
