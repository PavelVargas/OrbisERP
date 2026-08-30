(() => {
  'use strict';
  const root = document.documentElement;
  const body = document.body;
  const $ = (id) => document.getElementById(id);

  const currentTheme = () => root.classList.contains('dark') ? 'dark' : 'light';
  const paintThemeButton = () => {
    const dark = currentTheme() === 'dark';
    const icon = $('themeIco'); const text = $('themeTxt');
    if (icon) icon.className = dark ? 'bi bi-sun' : 'bi bi-moon';
    if (text) text.textContent = dark ? 'Modo claro' : 'Modo oscuro';
  };
  paintThemeButton();
  $('themeBtn')?.addEventListener('click', () => {
    const next = currentTheme() === 'dark' ? 'light' : 'dark';
    if (window.OrbisTheme) window.OrbisTheme.set(next);
    else {
      root.classList.toggle('dark', next === 'dark'); root.dataset.theme = next;
      try { localStorage.setItem('theme', next); localStorage.setItem('orbis-theme', next); document.cookie = `orbis_theme=${next}; Path=/; Max-Age=31536000; SameSite=Lax`; } catch (_e) {}
    }
    paintThemeButton();
  });
  document.addEventListener('orbis:themechange', paintThemeButton);

  const openModal = (id) => {
    const modal = $(id); if (!modal) return;
    modal.hidden = false; body.style.overflow = 'hidden';
    modal.querySelector('button,input,select,textarea')?.focus();
  };
  const closeModal = (id) => {
    const modal = $(id); if (!modal) return;
    modal.hidden = true;
    if (!document.querySelector('.sa-modal-backdrop:not([hidden])')) body.style.overflow = '';
  };
  document.querySelectorAll('[data-open-modal]').forEach(btn => btn.addEventListener('click', () => openModal(btn.dataset.openModal)));
  document.querySelectorAll('[data-open-client]').forEach(btn => btn.addEventListener('click', () => openModal(btn.dataset.openClient)));
  document.querySelectorAll('[data-close-modal]').forEach(btn => btn.addEventListener('click', () => closeModal(btn.dataset.closeModal)));
  document.querySelectorAll('.sa-modal-backdrop').forEach(bg => bg.addEventListener('click', event => { if (event.target === bg) closeModal(bg.id); }));
  document.addEventListener('keydown', event => { if (event.key === 'Escape') document.querySelectorAll('.sa-modal-backdrop:not([hidden])').forEach(x => closeModal(x.id)); });

  const sidebar = $('saSidebar'); const backdrop = $('saBackdrop'); const menu = $('saMenuBtn');
  const closeSidebar = () => { sidebar?.classList.remove('open'); if (backdrop) backdrop.hidden = true; };
  menu?.addEventListener('click', () => { sidebar?.classList.toggle('open'); if (backdrop) backdrop.hidden = !sidebar?.classList.contains('open'); });
  backdrop?.addEventListener('click', closeSidebar);
  sidebar?.querySelectorAll('a').forEach(link => link.addEventListener('click', () => { if (innerWidth <= 760) closeSidebar(); }));

  requestAnimationFrame(() => root.classList.remove('theme-preload'));
})();
