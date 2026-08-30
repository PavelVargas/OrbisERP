(function () {
  'use strict';

  function currentTheme() {
    if (window.OrbisTheme && typeof window.OrbisTheme.get === 'function') {
      return window.OrbisTheme.get();
    }
    return document.documentElement.classList.contains('dark') ? 'dark' : 'light';
  }

  function applyFallback(theme) {
    var normalized = theme === 'dark' ? 'dark' : 'light';
    var dark = normalized === 'dark';
    var root = document.documentElement;
    root.classList.toggle('dark', dark);
    root.dataset.theme = normalized;
    root.style.colorScheme = normalized;
    root.style.setProperty('background-color', dark ? '#191b1f' : '#f5f7fa', 'important');
    try { document.cookie = 'orbis_theme=' + normalized + '; Path=/; Max-Age=31536000; SameSite=Lax'; } catch (_error) {}
    if (document.body) {
      document.body.classList.toggle('dark', dark);
      document.body.dataset.theme = normalized;
    }
    try {
      localStorage.setItem('theme', normalized);
      localStorage.setItem('orbis-theme', normalized);
    } catch (_error) {
      // Storage can be disabled; keep the current document synchronized.
    }
    document.dispatchEvent(new CustomEvent('orbis:themechange', { detail: { theme: normalized } }));
    return normalized;
  }

  function paintButton(button, theme) {
    if (!button) return;
    var dark = theme === 'dark';
    var icon = button.querySelector('i');
    var label = button.querySelector('.mode-text') || button.querySelector('#themeText');
    var actionLabel = dark ? 'Modo claro' : 'Modo oscuro';

    if (icon) icon.className = dark ? 'bi bi-sun-fill' : 'bi bi-moon-stars-fill';
    if (label) label.textContent = actionLabel;
    button.setAttribute('aria-label', dark ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro');
    button.setAttribute('title', dark ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro');
  }

  function init() {
    var button = document.getElementById('themeToggle') || document.getElementById('theme-toggle');
    if (!button) return;

    paintButton(button, currentTheme());
    button.addEventListener('click', function () {
      var next;
      if (window.OrbisTheme && typeof window.OrbisTheme.toggle === 'function') {
        next = window.OrbisTheme.toggle();
      } else {
        next = applyFallback(currentTheme() === 'dark' ? 'light' : 'dark');
      }
      paintButton(button, next);
    });

    document.addEventListener('orbis:themechange', function (event) {
      var theme = event.detail && event.detail.theme ? event.detail.theme : currentTheme();
      paintButton(button, theme);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
}());
