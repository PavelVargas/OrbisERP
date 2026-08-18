(() => {
    'use strict';

    const ready = (callback) => document.readyState === 'loading'
        ? document.addEventListener('DOMContentLoaded', callback, { once: true })
        : callback();

    ready(() => {
        const sidebar = document.getElementById('app-sidebar');
        const mobileButton = document.getElementById('sidebar-toggle');
        const collapseButton = document.getElementById('collapse-toggle');
        const overlay = document.getElementById('sidebar-overlay');
        const themeButton = document.getElementById('theme-switch');
        const search = document.getElementById('nav-search');
        const navEmpty = document.getElementById('nav-empty');
        if (!sidebar) return;

        const desktop = () => window.innerWidth > 1024;
        const setCollapsed = (collapsed) => {
            const enabled = desktop() && collapsed;
            sidebar.classList.toggle('collapsed', enabled);
            document.documentElement.classList.toggle('sidebar-collapsed', enabled);
            collapseButton?.setAttribute('aria-label', enabled ? 'Expandir menú' : 'Contraer menú');
        };
        const closeMobile = () => {
            sidebar.classList.remove('mobile-open');
            overlay?.classList.remove('active');
            mobileButton?.setAttribute('aria-expanded', 'false');
        };

        setCollapsed(localStorage.getItem('sidebar-collapsed') === 'true');

        collapseButton?.addEventListener('click', () => {
            const collapsed = !sidebar.classList.contains('collapsed');
            localStorage.setItem('sidebar-collapsed', String(collapsed));
            setCollapsed(collapsed);
            setTimeout(() => dispatchEvent(new Event('resize')), 230);
        });

        mobileButton?.addEventListener('click', () => {
            const open = sidebar.classList.toggle('mobile-open');
            overlay?.classList.toggle('active', open);
            mobileButton.setAttribute('aria-expanded', String(open));
        });
        overlay?.addEventListener('click', closeMobile);
        sidebar.querySelectorAll('a.nav-item').forEach((item) => item.addEventListener('click', closeMobile));

        themeButton?.addEventListener('click', () => {
            const dark = !document.documentElement.classList.contains('dark');
            document.documentElement.classList.toggle('dark', dark);
            document.documentElement.style.colorScheme = dark ? 'dark' : 'light';
            localStorage.setItem('theme', dark ? 'dark' : 'light');
        });

        const filterNavigation = () => {
            const query = (search?.value || '').trim().toLocaleLowerCase('es');
            let matches = 0;
            sidebar.querySelectorAll('[data-nav-group]').forEach((group) => {
                let groupMatches = 0;
                group.querySelectorAll('[data-nav-label]').forEach((item) => {
                    const visible = !query || item.dataset.navLabel.includes(query) || item.textContent.toLocaleLowerCase('es').includes(query);
                    item.hidden = !visible;
                    if (visible) groupMatches += 1;
                });
                group.hidden = groupMatches === 0;
                matches += groupMatches;
            });
            if (navEmpty) navEmpty.hidden = matches !== 0;
        };
        search?.addEventListener('input', filterNavigation);

        document.addEventListener('keydown', (event) => {
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
                event.preventDefault();
                if (sidebar.classList.contains('collapsed')) setCollapsed(false);
                search?.focus();
            }
            if (event.key === 'Escape') {
                closeMobile();
                if (document.activeElement === search) {
                    search.value = '';
                    filterNavigation();
                    search.blur();
                }
            }
        });

        let resizeTimer;
        addEventListener('resize', () => {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(() => {
                closeMobile();
                setCollapsed(localStorage.getItem('sidebar-collapsed') === 'true');
            }, 100);
        });
    });
})();
