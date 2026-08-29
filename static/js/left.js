(() => {
    'use strict';

    const SVG_NS = 'http://www.w3.org/2000/svg';
    const paths = Object.freeze({
        dashboard: ['M4 4h6v6H4z M14 4h6v6h-6z M4 14h6v6H4z M14 14h6v6h-6z'],
        plus: ['M12 5v14 M5 12h14'],
        receipt: ['M6 3h12v18l-3-2-3 2-3-2-3 2V3z M9 8h6 M9 12h6 M9 16h3'],
        users: ['M16 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2 M9.5 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M17 11a3 3 0 0 0 0-6 M21 21v-2a4 4 0 0 0-3-3.87'],
        crm: ['M21 11.5a8.4 8.4 0 0 1-9 8.5 9.8 9.8 0 0 1-4-.85L3 21l1.85-4A8.7 8.7 0 1 1 21 11.5z M8.2 10.6c.8-1.2 2.5-.8 2.8.45.3-1.25 2-1.65 2.8-.45.9 1.45-1.1 3.1-2.8 4.25-1.7-1.15-3.7-2.8-2.8-4.25z'],
        shield: ['M12 3l7 3v5c0 5-3 8-7 10-4-2-7-5-7-10V6l7-3z M9 12l2 2 4-4'],
        box: ['M4 7l8-4 8 4-8 4-8-4z M4 7v10l8 4 8-4V7 M12 11v10'],
        tag: ['M4 4h7l9 9-7 7-9-9V4z M8 8h.01'],
        building: ['M4 21V5l8-3 8 3v16 M8 8h.01 M12 8h.01 M16 8h.01 M8 12h.01 M12 12h.01 M16 12h.01 M9 21v-5h6v5'],
        transfer: ['M7 7h13 M16 3l4 4-4 4 M17 17H4 M8 13l-4 4 4 4'],
        scan: ['M4 8V4h4 M16 4h4v4 M20 16v4h-4 M8 20H4v-4 M7 12h10 M9 9v6 M12 9v6 M15 9v6'],
        inventory: ['M4 8l8-4 8 4-8 4-8-4z M4 8v8l8 4 8-4V8 M8 10v8 M16 10v8'],
        clipboard: ['M9 4h6l1 2h3v15H5V6h3l1-2z M9 12l2 2 4-4 M9 17h6'],
        list: ['M9 6h11 M9 12h11 M9 18h11 M4 6h.01 M4 12h.01 M4 18h.01'],
        barcode: ['M4 5v14 M7 5v14 M11 5v14 M14 5v14 M18 5v14 M20 5v14'],
        purchase: ['M5 7h14l-1 12H6L5 7z M9 7V5a3 3 0 0 1 6 0v2 M9 12h6'],
        truck: ['M3 6h11v10H3z M14 9h4l3 4v3h-7z M7 20a2 2 0 1 0 0-4 2 2 0 0 0 0 4z M18 20a2 2 0 1 0 0-4 2 2 0 0 0 0 4z'],
        chart: ['M4 20V10 M10 20V4 M16 20v-7 M22 20H2'],
        cash: ['M4 6h16v12H4z M8 12h.01 M16 12h.01 M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z'],
        command: ['M9 4a3 3 0 1 0-3 3h3V4z M15 4v3h3a3 3 0 1 0-3-3z M9 17H6a3 3 0 1 0 3 3v-3z M15 17v3a3 3 0 1 0 3-3h-3z M9 7h6v10H9z'],
        settings: ['M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2 3.46-.08-.02a1.7 1.7 0 0 0-1.8.28l-.64.38a1.7 1.7 0 0 0-.82 1.62V22h-4v-.08a1.7 1.7 0 0 0-.82-1.62L9 19.92a1.7 1.7 0 0 0-1.8-.28l-.08.02-2-3.46.06-.06A1.7 1.7 0 0 0 5.6 15v-.75a1.7 1.7 0 0 0-.42-1.14l-.06-.06 2-3.46.08.02A1.7 1.7 0 0 0 9 9.33l.64-.38a1.7 1.7 0 0 0 .82-1.62V7h4v.08a1.7 1.7 0 0 0 .82 1.62l.64.38a1.7 1.7 0 0 0 1.8.28l.08-.02 2 3.46-.06.06a1.7 1.7 0 0 0-.34 1.88V15z'],
        star: ['M12 3l2.7 5.5 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1-4.4-4.3 6.1-.9L12 3z'],
        card: ['M3 6h18v12H3z M3 10h18 M7 15h4'],
        import: ['M7 7h10 M12 3v8 M8 7l4 4 4-4 M5 15v4h14v-4'],
        percent: ['M7 7h.01 M17 17h.01 M18 6L6 18'],
        ticket: ['M4 7h16v4a2 2 0 0 0 0 4v4H4v-4a2 2 0 0 0 0-4v-4a2 2 0 0 0 0 4V7z M12 8v2 M12 14v2 M12 18v1'],
        shop: ['M4 10v10h16V10 M3 10l2-6h14l2 6 M8 20v-6h8v6 M5 10a3 3 0 0 0 6 0 3 3 0 0 0 6 0 3 3 0 0 0 4 0'],
        printer: ['M6 9V3h12v6 M6 17H4a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-2 M6 14h12v7H6z M18 12h.01'],
        folder: ['M3 6h7l2 2h9v11H3z'],
        trash: ['M4 7h16 M9 7V4h6v3 M7 7l1 14h8l1-14 M10 11v6 M14 11v6'],
        usergear: ['M9 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M3 21v-2a6 6 0 0 1 6-6h2 M17 14a3 3 0 1 0 0 6 3 3 0 0 0 0-6z M17 12v2 M17 20v2 M12 17h2 M20 17h2'],
        tablet: ['M5 3h14v18H5z M10 18h4'],
        bell: ['M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9z M10 21h4'],
        journal: ['M5 3h14v18H5z M9 7h6 M9 11h6 M9 15h4 M3 6h4 M3 10h4 M3 14h4 M3 18h4'],
        activity: ['M3 12h4l2-6 4 12 2-6h6'],
        search: ['M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14z M20 20l-4-4'],
        chevronDown: ['M6 9l6 6 6-6'],
        chevronLeft: ['M15 18l-6-6 6-6'],
        chevronRight: ['M9 18l6-6-6-6'],
        check: ['M5 12l4 4L19 6'],
        lock: ['M7 10V7a5 5 0 0 1 10 0v3 M5 10h14v11H5z M12 14v3'],
        megaphone: ['M4 11v3l10 4V7L4 11z M14 9l5-2v11l-5-2 M6 15l1 5h4l-2-4'],
        desktop: ['M3 4h18v13H3z M8 21h8 M12 17v4'],
        logout: ['M10 5H5v14h5 M14 8l4 4-4 4 M18 12H9'],
        moon: ['M20 15.2A8.5 8.5 0 0 1 8.8 4 8.5 8.5 0 1 0 20 15.2z'],
        sun: ['M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z M12 2v2 M12 20v2 M4.9 4.9l1.4 1.4 M17.7 17.7l1.4 1.4 M2 12h2 M20 12h2 M4.9 19.1l1.4-1.4 M17.7 6.3l1.4-1.4'],
        x: ['M6 6l12 12 M18 6L6 18'],
        info: ['M12 10v7 M12 7h.01 M3 12a9 9 0 1 0 18 0 9 9 0 0 0-18 0z'],
        warning: ['M12 3l10 18H2L12 3z M12 9v5 M12 18h.01'],
        edit: ['M4 20h4l11-11-4-4L4 16v4z M13 7l4 4'],
        eye: ['M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z'],
        clock: ['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z M12 6v6l4 2'],
        calendar: ['M4 5h16v16H4z M8 3v4 M16 3v4 M4 9h16'],
        download: ['M12 3v12 M7 10l5 5 5-5 M4 21h16'],
        upload: ['M12 21V9 M7 14l5-5 5 5 M4 3h16'],
        mail: ['M3 5h18v14H3z M3 7l9 7 9-7'],
        filter: ['M3 5h18l-7 8v6l-4 2v-8L3 5z'],
        home: ['M3 11l9-8 9 8v10h-6v-6H9v6H3z'],
        save: ['M4 3h14l2 2v16H4z M8 3v6h8V3 M8 21v-7h8v7'],
        phone: ['M7 3h3l2 5-2 2a15 15 0 0 0 4 4l2-2 5 2v3c0 2-2 4-4 4C9 20 4 15 3 7c0-2 2-4 4-4z'],
        image: ['M4 4h16v16H4z M8 10a2 2 0 1 0 0-4 2 2 0 0 0 0 4z M4 17l5-5 4 4 2-2 5 5'],
        generic: ['M5 5h14v14H5z M9 9h6v6H9z']
    });

    const aliases = Object.freeze({
        'bi-grid-1x2-fill': 'dashboard', 'bi-grid-fill': 'dashboard', 'bi-grid-3x3-gap-fill': 'dashboard',
        'bi-plus-lg': 'plus', 'bi-receipt': 'receipt', 'bi-people': 'users',
        'bi-chat-square-heart': 'crm', 'bi-shield-check': 'shield', 'bi-shield-lock-fill': 'shield',
        'bi-box-seam': 'box', 'bi-tags': 'tag', 'bi-building': 'building',
        'bi-arrow-left-right': 'transfer', 'bi-arrow-down-up': 'import', 'bi-upc-scan': 'scan',
        'bi-upc': 'barcode', 'bi-boxes': 'inventory', 'bi-clipboard2-pulse': 'clipboard',
        'bi-clipboard2-check': 'clipboard', 'bi-list-check': 'list', 'bi-list-task': 'list',
        'bi-bag-check': 'purchase', 'bi-truck': 'truck', 'bi-bar-chart': 'chart',
        'bi-cash-coin': 'cash', 'bi-command': 'command', 'bi-gear': 'settings',
        'bi-stars': 'star', 'bi-credit-card': 'card', 'bi-percent': 'percent',
        'bi-ticket-perforated': 'ticket', 'bi-shop-window': 'shop', 'bi-printer': 'printer',
        'bi-folder2-open': 'folder', 'bi-trash3': 'trash', 'bi-person-gear': 'usergear',
        'bi-tablet-landscape': 'tablet', 'bi-bell': 'bell', 'bi-bell-fill': 'bell',
        'bi-journal-text': 'journal', 'bi-activity': 'activity', 'bi-display': 'tablet',
        'bi-cash-stack': 'cash', 'bi-list': 'list', 'bi-lock-fill': 'lock',
        'bi-megaphone-fill': 'megaphone', 'bi-pc-display': 'desktop',
        'bi-box-arrow-right': 'logout', 'bi-moon-stars': 'moon', 'bi-sun': 'sun',
        'bi-search': 'search', 'bi-chevron-down': 'chevronDown',
        'bi-chevron-left': 'chevronLeft', 'bi-chevron-right': 'chevronRight',
        'bi-check': 'check', 'bi-check-circle': 'check'
    });

    function resolveName(value) {
        const token = String(value || '').split(/\s+/).find(part => part.startsWith('bi-')) || String(value || '');
        if (aliases[token] || paths[token]) return aliases[token] || token;
        const name = token.toLowerCase();
        if (/check|patch-check/.test(name)) return 'check';
        if (/x-|x$|close|dash-circle|slash-circle/.test(name)) return 'x';
        if (/exclamation|warning/.test(name)) return 'warning';
        if (/info|lightbulb/.test(name)) return 'info';
        if (/pencil|edit|eraser/.test(name)) return 'edit';
        if (/eye/.test(name)) return 'eye';
        if (/clock|history|hourglass/.test(name)) return 'clock';
        if (/calendar/.test(name)) return 'calendar';
        if (/cloud-arrow-up|upload|arrow-up-circle|file-earmark-arrow-up/.test(name)) return 'upload';
        if (/download|arrow-down-circle|file-earmark-arrow-down/.test(name)) return 'download';
        if (/envelope|send|inbox|chat/.test(name)) return 'mail';
        if (/funnel|slider/.test(name)) return 'filter';
        if (/house|home/.test(name)) return 'home';
        if (/save/.test(name)) return 'save';
        if (/telephone|phone|whatsapp/.test(name)) return 'phone';
        if (/image|camera/.test(name)) return 'image';
        if (/person|people|user/.test(name)) return 'users';
        if (/shield/.test(name)) return 'shield';
        if (/lock|key|fingerprint/.test(name)) return 'lock';
        if (/building|shop|store/.test(name)) return 'building';
        if (/cash|wallet|currency|bank|credit-card/.test(name)) return 'cash';
        if (/truck/.test(name)) return 'truck';
        if (/printer/.test(name)) return 'printer';
        if (/receipt|file|journal|clipboard|card-text/.test(name)) return 'receipt';
        if (/chart|graph|pie|speedometer/.test(name)) return 'chart';
        if (/box|bag|basket|archive|layers/.test(name)) return 'box';
        if (/tag|ticket|gift|star/.test(name)) return 'tag';
        if (/gear|tools|wrench|cpu|device/.test(name)) return 'settings';
        if (/grid|kanban/.test(name)) return 'dashboard';
        if (/arrow-left-right|repeat|counterclockwise|clockwise/.test(name)) return 'transfer';
        if (/arrow-left|return-left/.test(name)) return 'chevronLeft';
        if (/arrow-right/.test(name)) return 'chevronRight';
        if (/plus/.test(name)) return 'plus';
        if (/trash/.test(name)) return 'trash';
        return 'generic';
    }

    function create(value, className = 'orbis-line-icon') {
        const svg = document.createElementNS(SVG_NS, 'svg');
        svg.setAttribute('viewBox', '0 0 24 24');
        svg.setAttribute('aria-hidden', 'true');
        svg.setAttribute('focusable', 'false');
        svg.classList.add(className);
        for (const d of paths[resolveName(value)] || paths.generic) {
            const path = document.createElementNS(SVG_NS, 'path');
            path.setAttribute('d', d);
            svg.append(path);
        }
        return svg;
    }

    window.OrbisLocalIcons = Object.freeze({create});
})();

(() => {
    'use strict';

    const ready = (callback) => document.readyState === 'loading'
        ? document.addEventListener('DOMContentLoaded', callback, { once: true })
        : callback();

    // Access to Web Storage can throw in private browsing, hardened kiosk
    // profiles, embedded/opaque origins, or when a browser policy disables it.
    // Navigation must remain fully usable even when persistence is unavailable.
    const storageRead = (kind, key, fallback = null) => {
        try {
            const store = window[kind];
            const value = store?.getItem(key);
            return value === null || value === undefined ? fallback : value;
        } catch (_error) {
            return fallback;
        }
    };
    const storageWrite = (kind, key, value) => {
        try {
            window[kind]?.setItem(key, String(value));
            return true;
        } catch (_error) {
            return false;
        }
    };

    ready(() => {
        const sidebar = document.getElementById('app-sidebar');
        const mobileButton = document.getElementById('sidebar-toggle');
        const collapseButton = document.getElementById('collapse-toggle');
        const overlay = document.getElementById('sidebar-overlay');
        const themeButton = document.getElementById('theme-switch');
        const search = document.getElementById('nav-search');
        const navEmpty = document.getElementById('nav-empty');
        const navScroller = sidebar?.querySelector('.sidebar-nav');
        if (!sidebar) return;

        // Navigation icons are rendered locally as inline SVG, so the menu keeps
        // its meaning and visual hierarchy even when the public icon CDN is blocked.
        sidebar.querySelectorAll('.nav-item .nav-icon').forEach((shell) => {
            const originalIcons = Array.from(shell.querySelectorAll('i'));
            if (!originalIcons.length) return;
            const icons = originalIcons.map((icon) => {
                const svg = window.OrbisLocalIcons?.create(icon.className || 'bi-generic', 'orbis-nav-icon');
                if (!svg) return null;
                if (icon.classList.contains('theme-moon')) svg.classList.add('theme-moon');
                if (icon.classList.contains('theme-sun')) svg.classList.add('theme-sun');
                return svg;
            }).filter(Boolean);
            if (icons.length) shell.replaceChildren(...icons);
        });

        document.querySelectorAll([
            '.sidebar-mobile-trigger i.bi',
            '.collapse-btn i.bi',
            '.section-title.nav-section-toggle i.bi',
            '.sidebar-search > i.bi',
            '.global-search-box > i.bi',
            '.app-tablet-topbar i.bi',
            '.app-tablet-dock i.bi',
            '.tablet-section-sheet i.bi'
        ].join(',')).forEach((icon) => {
            const svg = window.OrbisLocalIcons?.create(icon.className, 'orbis-shell-icon');
            if (svg) icon.replaceWith(svg);
        });

        const bootstrapIconsAvailable = () => {
            const probe = document.createElement('i');
            probe.className = 'bi bi-check';
            probe.style.cssText = 'position:absolute;visibility:hidden;pointer-events:none';
            document.body.append(probe);
            const content = getComputedStyle(probe, '::before').content;
            probe.remove();
            return Boolean(content && content !== 'none' && content !== 'normal' && content !== '""');
        };
        const iconFontAvailable = bootstrapIconsAvailable();
        if (!iconFontAvailable) {
            document.documentElement.classList.add('icons-fallback');
            document.querySelectorAll([
                'main i.bi',
                '.company-readonly-banner i.bi',
                '.global-broadcast-banner i.bi',
                '.support-mode i.bi'
            ].join(',')).forEach((icon) => {
                const svg = window.OrbisLocalIcons?.create(icon.className, 'orbis-content-icon');
                if (!svg) return;
                const label = icon.getAttribute('aria-label');
                const title = icon.getAttribute('title');
                if (label) svg.setAttribute('aria-label', label);
                if (title) svg.setAttribute('title', title);
                icon.replaceWith(svg);
            });
        }

        // Preserve the exact menu position between full-page navigations.
        // Without this, selecting an item near the bottom makes the refreshed
        // sidebar jump back to the first option.
        const scrollKey = 'orbis-sidebar-scroll';
        if (navScroller) {
            const savedScroll = Number(storageRead('sessionStorage', scrollKey, '0') || 0);
            requestAnimationFrame(() => {
                navScroller.scrollTop = Number.isFinite(savedScroll) ? savedScroll : 0;
                if (!savedScroll) sidebar.querySelector('a.nav-item.active')?.scrollIntoView({ block: 'nearest' });
            });
            let scrollTimer;
            navScroller.addEventListener('scroll', () => {
                clearTimeout(scrollTimer);
                scrollTimer = setTimeout(() => storageWrite('sessionStorage', scrollKey, navScroller.scrollTop), 40);
            }, { passive: true });
            sidebar.querySelectorAll('a.nav-item').forEach((item) => item.addEventListener('click', () => {
                storageWrite('sessionStorage', scrollKey, navScroller.scrollTop);
            }));
        }

        const desktop = () => window.innerWidth > 1024 && !document.documentElement.classList.contains('tablet-mode');
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

        setCollapsed(storageRead('localStorage', 'sidebar-collapsed', 'false') === 'true');

        const navSectionKey = 'orbis-nav-sections-v3';
        const navSections = Array.from(sidebar.querySelectorAll('[data-nav-section]'));
        const storedSectionState = (() => {
            try {
                const raw = storageRead('localStorage', navSectionKey);
                if (raw === null) {
                    // A first-time user should see a focused menu, not every
                    // administrative section expanded at once. Keep only the
                    // section containing the current page open by default.
                    const initial = new Set(
                        navSections
                            .filter(section => !section.querySelector('.nav-item.active'))
                            .map(section => String(section.dataset.navSection || ''))
                            .filter(Boolean)
                    );
                    storageWrite('localStorage', navSectionKey, JSON.stringify(Array.from(initial)));
                    return initial;
                }
                const parsed = JSON.parse(raw);
                return new Set(Array.isArray(parsed) ? parsed.map(String) : []);
            } catch (_error) {
                return new Set();
            }
        })();
        const syncSection = (section, collapsed, {persist = true} = {}) => {
            const name = String(section.dataset.navSection || '');
            const hasActiveItem = Boolean(section.querySelector('.nav-item.active'));
            const nextCollapsed = Boolean(collapsed && !hasActiveItem);
            section.classList.toggle('is-collapsed', nextCollapsed);
            section.querySelector('.nav-section-toggle')?.setAttribute('aria-expanded', String(!nextCollapsed));
            if (!persist || !name) return;
            if (nextCollapsed) storedSectionState.add(name);
            else storedSectionState.delete(name);
            storageWrite('localStorage', navSectionKey, JSON.stringify(Array.from(storedSectionState)))
        };
        navSections.forEach((section) => {
            syncSection(section, storedSectionState.has(String(section.dataset.navSection)), {persist: false});
            section.querySelector('.nav-section-toggle')?.addEventListener('click', () => {
                syncSection(section, !section.classList.contains('is-collapsed'));
            });
        });

        collapseButton?.addEventListener('click', () => {
            const collapsed = !sidebar.classList.contains('collapsed');
            storageWrite('localStorage', 'sidebar-collapsed', collapsed);
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
            if (window.OrbisTheme) {
                window.OrbisTheme.toggle();
                return;
            }
            const root = document.documentElement;
            const dark = !root.classList.contains('dark');
            const theme = dark ? 'dark' : 'light';
            root.classList.toggle('dark', dark);
            root.dataset.theme = theme;
            root.style.colorScheme = theme;
            document.body?.classList.toggle('dark', dark);
            if (document.body) document.body.dataset.theme = theme;
            storageWrite('localStorage', 'theme', theme);
            storageWrite('localStorage', 'orbis-theme', theme);
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
                if (query && groupMatches) syncSection(group, false, {persist: false});
                else if (!query && group.dataset.navSection) {
                    syncSection(group, storedSectionState.has(String(group.dataset.navSection)), {persist: false});
                }
                matches += groupMatches;
            });
            if (navEmpty) navEmpty.hidden = matches !== 0;
        };
        search?.addEventListener('input', filterNavigation);

        document.addEventListener('keydown', (event) => {
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
                setCollapsed(storageRead('localStorage', 'sidebar-collapsed', 'false') === 'true');
            }, 100);
        });

        // Back links should return to the page the user actually came from.
        // Their href remains a reliable fallback for bookmarks/direct access.
        document.querySelectorAll('a').forEach((link) => {
            const looksLikeBack = link.matches('.workspace-back, .ops-back, .back-link, .reports-back') || /^volver\b/i.test((link.textContent || '').trim());
            if (!looksLikeBack) return;
            link.addEventListener('click', (event) => {
                if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
                try {
                    const ref = document.referrer ? new URL(document.referrer) : null;
                    if (ref && ref.origin === location.origin && ref.href !== location.href) {
                        event.preventDefault();
                        history.back();
                    }
                } catch (_) {}
            });
        });
    });
})();

(() => {
    'use strict';

    const init = () => {
        const modal = document.getElementById('global-search-modal');
        const input = document.getElementById('global-search-input');
        const results = document.getElementById('global-search-results');
        if (!modal || !input || !results) return;

        let timer;
        let requestController;
        let activeIndex = -1;
        let lastFocused = null;

        const resultLinks = () => [...results.querySelectorAll('.global-search-result')];
        const setActive = (index) => {
            const links = resultLinks();
            if (!links.length) { activeIndex = -1; return; }
            activeIndex = Math.max(0, Math.min(index, links.length - 1));
            links.forEach((link, idx) => {
                const active = idx === activeIndex;
                link.classList.toggle('is-active', active);
                link.setAttribute('aria-selected', String(active));
            });
            links[activeIndex]?.scrollIntoView({block: 'nearest'});
        };
        const emptyMessage = (title, message = '') => {
            activeIndex = -1;
            const wrap = document.createElement('div');
            wrap.className = 'search-empty';
            const icon = document.createElement('span');
            const glyph = window.OrbisLocalIcons?.create('bi-search', 'orbis-search-empty-icon');
            if (glyph) icon.append(glyph); else icon.textContent = '⌕';
            const strong = document.createElement('strong');
            strong.textContent = title;
            wrap.append(icon, strong);
            if (message) {
                const small = document.createElement('small');
                small.textContent = message;
                wrap.append(small);
            }
            results.replaceChildren(wrap);
        };
        const close = () => {
            requestController?.abort();
            clearTimeout(timer);
            modal.classList.remove('open');
            modal.setAttribute('aria-hidden', 'true');
            document.documentElement.classList.remove('global-search-open');
            input.value = '';
            emptyMessage('¿Qué necesitas encontrar?', 'Escribe al menos 2 caracteres para empezar.');
            const focusTarget = lastFocused;
            lastFocused = null;
            if (focusTarget && typeof focusTarget.focus === 'function') setTimeout(() => focusTarget.focus(), 0);
        };
        const open = () => {
            if (modal.classList.contains('open')) return input.focus();
            lastFocused = document.activeElement;
            modal.classList.add('open');
            modal.setAttribute('aria-hidden', 'false');
            document.documentElement.classList.add('global-search-open');
            setTimeout(() => input.focus(), 0);
        };
        const resultInitials = (label) => {
            const words = String(label || '').trim().split(/\s+/).filter(Boolean);
            return words.slice(0, 2).map(word => Array.from(word)[0] || '').join('').toLocaleUpperCase('es') || 'R';
        };
        const safeInternalUrl = (value) => {
            try {
                const url = new URL(String(value || '/'), window.location.origin);
                if (url.origin !== window.location.origin || !['http:', 'https:'].includes(url.protocol)) return '#';
                return `${url.pathname}${url.search}${url.hash}`;
            } catch (_error) {
                return '#';
            }
        };
        const buildResult = (row, index) => {
            const link = document.createElement('a');
            link.className = 'global-search-result';
            link.href = safeInternalUrl(row?.url);
            link.setAttribute('role', 'option');
            link.setAttribute('aria-selected', 'false');
            link.dataset.resultIndex = String(index);

            const icon = document.createElement('span');
            icon.className = 'global-search-result-icon';
            icon.setAttribute('aria-hidden', 'true');
            const requestedIcon = String(row?.icon || 'bi-search');
            const localGlyph = window.OrbisLocalIcons?.create(requestedIcon, 'orbis-search-icon');
            if (localGlyph) icon.append(localGlyph);
            else icon.textContent = resultInitials(String(row?.type || row?.title || 'R'));

            const copy = document.createElement('span');
            copy.className = 'global-search-result-copy';
            const title = document.createElement('strong');
            title.textContent = String(row?.title || 'Resultado');
            const meta = document.createElement('small');
            meta.textContent = String(row?.subtitle || '').trim() || 'Abrir registro';
            copy.append(title, meta);

            const type = document.createElement('span');
            type.className = 'global-search-result-type';
            type.textContent = String(row?.type || 'Registro');
            const arrow = document.createElement('i');
            arrow.className = 'bi bi-arrow-up-right';
            type.append(arrow);

            link.append(icon, copy, type);
            link.addEventListener('mouseenter', () => setActive(index));
            return link;
        };

        document.querySelectorAll('[data-global-search-trigger]').forEach(button => button.addEventListener('click', open));
        document.querySelectorAll('[data-global-search-close]').forEach(button => button.addEventListener('click', close));
        document.getElementById('tablet-search-trigger')?.addEventListener('click', open);
        document.addEventListener('keydown', (event) => {
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
                event.preventDefault();
                event.stopImmediatePropagation();
                open();
                return;
            }
            if (!modal.classList.contains('open')) return;
            if (event.key === 'Escape') { event.preventDefault(); close(); return; }
            if (event.key === 'ArrowDown') { event.preventDefault(); setActive(activeIndex < 0 ? 0 : activeIndex + 1); return; }
            if (event.key === 'ArrowUp') { event.preventDefault(); setActive(activeIndex < 0 ? 0 : activeIndex - 1); return; }
            if (event.key === 'Enter' && activeIndex >= 0) {
                const target = resultLinks()[activeIndex];
                if (target) { event.preventDefault(); target.click(); }
            }
        }, true);
        modal.addEventListener('click', (event) => { if (event.target === modal) close(); });
        input.addEventListener('input', () => {
            clearTimeout(timer);
            requestController?.abort();
            const query = input.value.trim();
            if (query.length < 2) {
                emptyMessage('Sigue escribiendo', 'Necesitamos al menos 2 caracteres.');
                return;
            }
            emptyMessage('Buscando…', 'Estamos revisando productos, clientes y operaciones.');
            timer = setTimeout(async () => {
                requestController = new AbortController();
                try {
                    const url = new URL('/workspace/search', window.location.origin);
                    url.searchParams.set('q', query);
                    const response = await fetch(url, {
                        headers: {'Accept': 'application/json'},
                        credentials: 'same-origin',
                        signal: requestController.signal
                    });
                    if (!response.ok) throw new Error(`Búsqueda HTTP ${response.status}`);
                    const payload = await response.json();
                    const rows = Array.isArray(payload?.results) ? payload.results : [];
                    if (!rows.length) {
                        emptyMessage('Sin resultados', `No encontramos coincidencias para “${query}”.`);
                        return;
                    }
                    results.replaceChildren(...rows.slice(0, 24).map(buildResult));
                    setActive(0);
                } catch (error) {
                    if (error?.name === 'AbortError') return;
                    console.error('No fue posible completar la búsqueda global:', error);
                    emptyMessage('No pudimos buscar', 'Inténtalo de nuevo en unos segundos.');
                }
            }, 150);
        });
    };

    document.readyState === 'loading'
        ? document.addEventListener('DOMContentLoaded', init, {once: true})
        : init();
})();

// ORBIS_SCANNER_NAV_EXCLUSIVITY_20260825
(function () {
  'use strict';
  function normalizedPath(anchor) {
    try { return new URL(anchor.href, window.location.origin).pathname.replace(/\/$/, '') || '/'; }
    catch (_) { return ''; }
  }
  function setScannerNavState() {
    var current = window.location.pathname.replace(/\/$/, '') || '/';
    if (!/^\/transfers\/(?:scanner|scanner-mode)(?:\/|$)/.test(current)) return;
    var anchors = Array.prototype.slice.call(document.querySelectorAll('a[href]'));
    var scanner = null;
    anchors.forEach(function (anchor) {
      var path = normalizedPath(anchor);
      var isScanner = /^\/transfers\/(?:scanner|scanner-mode)(?:\/|$)/.test(path);
      var isTransferParent = /^\/transfers(?:\/|$)/.test(path) && !isScanner;
      if (isTransferParent) {
        anchor.classList.remove('active', 'is-active', 'current', 'selected', 'menu-active');
        var parent = anchor.closest('li, .nav-item, .menu-item');
        if (parent) parent.classList.remove('active', 'is-active', 'current', 'selected', 'menu-active');
      }
      if (isScanner) scanner = anchor;
    });
    if (scanner) {
      scanner.classList.add('active');
      var scannerParent = scanner.closest('li, .nav-item, .menu-item');
      if (scannerParent) scannerParent.classList.add('active');
    }
    document.body.classList.add('scanner-mode-page');
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', setScannerNavState, { once: true });
  else setScannerNavState();
})();
