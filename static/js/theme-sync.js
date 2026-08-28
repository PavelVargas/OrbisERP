(function () {
  'use strict';

  var KEY = 'theme';
  var LEGACY_KEY = 'orbis-theme';
  var applying = false;

  function normalize(value) {
    return value === 'dark' ? 'dark' : value === 'light' ? 'light' : null;
  }

  function preferredTheme() {
    var stored = null;
    try {
      stored = normalize(localStorage.getItem(KEY)) || normalize(localStorage.getItem(LEGACY_KEY));
    } catch (_error) {
      stored = null;
    }
    if (stored) return stored;
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  function applyTheme(theme, persist) {
    theme = normalize(theme) || preferredTheme();
    if (applying) return theme;
    applying = true;
    var dark = theme === 'dark';
    var root = document.documentElement;
    if (root.classList.contains('dark') !== dark) root.classList.toggle('dark', dark);
    if (root.dataset.theme !== theme) root.dataset.theme = theme;
    if (root.style.colorScheme !== theme) root.style.colorScheme = theme;
    if (document.body) {
      if (document.body.classList.contains('dark') !== dark) document.body.classList.toggle('dark', dark);
      if (document.body.dataset.theme !== theme) document.body.dataset.theme = theme;
    }
    if (persist !== false) {
      try {
        localStorage.setItem(KEY, theme);
        localStorage.setItem(LEGACY_KEY, theme);
      } catch (_error) {
        // Storage can be disabled; the in-document theme still works.
      }
    }
    applying = false;
    document.dispatchEvent(new CustomEvent('orbis:themechange', { detail: { theme: theme } }));
    return theme;
  }

  function syncFromDom() {
    if (applying) return;
    var root = document.documentElement;
    var explicit = normalize(root.dataset.theme);
    var theme = root.classList.contains('dark') ? 'dark' : (explicit || 'light');
    applyTheme(theme, true);
  }

  function finishInitialPaint() {
    requestAnimationFrame(function () {
      requestAnimationFrame(function () { document.documentElement.classList.remove('theme-preload'); });
    });
  }

  applyTheme(preferredTheme(), false);
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { applyTheme(preferredTheme(), false); finishInitialPaint(); }, { once: true });
  } else {
    applyTheme(preferredTheme(), false);
    finishInitialPaint();
  }

  new MutationObserver(syncFromDom).observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['class', 'data-theme']
  });

  window.addEventListener('storage', function (event) {
    if (event.key === KEY || event.key === LEGACY_KEY) applyTheme(event.newValue, false);
  });

  window.OrbisTheme = Object.freeze({
    get: function () { return document.documentElement.classList.contains('dark') ? 'dark' : 'light'; },
    set: function (theme) { return applyTheme(theme, true); },
    toggle: function () { return applyTheme(window.OrbisTheme.get() === 'dark' ? 'light' : 'dark', true); }
  });
}());
