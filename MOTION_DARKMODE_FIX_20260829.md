# Dark mode / motion polish · 2026-08-29

- Eliminated dark-mode white flash by seeding the final canvas color before external CSS.
- The body remains hidden only during the theme bootstrap; it is revealed after the theme is stable.
- Browser `theme-color` now follows the active light/dark theme dynamically.
- `theme-sync.js` preserves the theme already chosen by the server/bootstrap and handles BFCache restores.
- Added progressive multi-page View Transitions for supported Chromium browsers.
- Added ~500 ms page-entry motion plus restrained micro-interactions for buttons, navigation, dialogs and popovers.
- `prefers-reduced-motion` disables non-essential motion.
