(() => {
  'use strict';
  const root = document.documentElement;
  const $ = (id) => document.getElementById(id);

  const storedTheme = () => {
    try { const value = localStorage.getItem('theme') || localStorage.getItem('orbis-theme'); if (['dark','light'].includes(value)) return value; } catch (_e) {}
    return root.dataset.theme === 'dark' || matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  };
  const setTheme = (theme) => {
    if (window.OrbisTheme) return window.OrbisTheme.set(theme);
    const dark = theme === 'dark';
    root.classList.toggle('dark', dark); root.dataset.theme = theme; root.style.colorScheme = theme;
    try { localStorage.setItem('theme', theme); localStorage.setItem('orbis-theme', theme); } catch (_e) {}
    return theme;
  };
  const updateThemeButton = (theme) => {
    const icon = $('themeIco'); const text = $('themeTxt');
    if (icon) icon.className = theme === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
    if (text) text.textContent = theme === 'dark' ? 'Usar modo claro' : 'Usar modo oscuro';
  };
  let theme = setTheme(storedTheme()); updateThemeButton(theme);
  $('themeBtn')?.addEventListener('click', () => { theme = setTheme(theme === 'dark' ? 'light' : 'dark'); updateThemeButton(theme); });
  document.addEventListener('orbis:themechange', (event) => { theme = event.detail?.theme || storedTheme(); updateThemeButton(theme); });

  const openBackdrop = (id) => { const el = $(id); if (!el) return; el.hidden = false; document.body.style.overflow = 'hidden'; el.querySelector('button,input,select,textarea')?.focus(); };
  const closeBackdrop = (id) => { const el = $(id); if (!el) return; el.hidden = true; if (!document.querySelector('.master-modal-backdrop:not([hidden])')) document.body.style.overflow = ''; };

  document.querySelector('[data-open-broadcast]')?.addEventListener('click', () => openBackdrop('broadcastModal'));
  document.querySelectorAll('[data-close-modal]').forEach((btn) => btn.addEventListener('click', () => closeBackdrop(btn.dataset.closeModal)));
  document.querySelectorAll('.master-modal-backdrop').forEach((backdrop) => backdrop.addEventListener('click', (event) => { if (event.target === backdrop) closeBackdrop(backdrop.id); }));
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') document.querySelectorAll('.master-modal-backdrop:not([hidden])').forEach((el) => closeBackdrop(el.id)); });

  document.querySelectorAll('.inspect-company').forEach((button) => button.addEventListener('click', () => {
    let data = {};
    try { data = JSON.parse(button.dataset.company || '{}'); } catch (_e) { return; }
    const assign = (id, value) => { const el = $(id); if (el) el.textContent = value ?? 'N/D'; };
    assign('m-name', data.name || 'Empresa'); assign('m-id', `#NODE-${String(data.id || 0).padStart(3,'0')}`);
    assign('m-status', data.status ? 'Activa' : 'Suspendida'); assign('m-readonly', data.is_readonly ? 'Solo lectura' : 'Acceso total');
    assign('m-plan', data.plan); assign('m-expiry', data.expiry); assign('m-rnc', data.rnc || 'N/D'); assign('m-tax', `${data.tax_name || 'Impuesto'} (${data.tax_percent || 0}%)`);
    assign('m-currency', data.currency); assign('m-usage', `${data.usage || 0} MB`); assign('m-email', data.email || 'N/D'); assign('m-address', data.address || 'N/D');
    const renew = $('renewForm'); if (renew) renew.action = button.dataset.renewUrl || '';
    openBackdrop('modalBg');
  }));

  const search = $('srch'); const empty = $('empty');
  const applySearch = () => {
    if (!search) return; const term = search.value.trim().toLocaleLowerCase('es'); let visible = 0;
    document.querySelectorAll('.nc').forEach((card) => { const haystack = `${card.dataset.name || ''} ${card.dataset.rnc || ''} ${card.dataset.admin || ''}`.toLocaleLowerCase('es'); const ok = !term || haystack.includes(term); card.hidden = !ok; if (ok) visible += 1; });
    if (empty) empty.style.display = visible ? 'none' : 'grid';
  };
  search?.addEventListener('input', applySearch);
  document.addEventListener('keydown', (event) => { if (event.key === '/' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || '')) { event.preventDefault(); search?.focus(); } });

  requestAnimationFrame(() => requestAnimationFrame(() => root.classList.remove('theme-preload')));
})();
