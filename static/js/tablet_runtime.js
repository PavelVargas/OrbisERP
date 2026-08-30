(() => {
    'use strict';

    const root = document.documentElement;
    if (!root.classList.contains('tablet-mode')) return;

    const TABLET_PREFERENCE_KEY = 'orbis-tablet-mode';
    const TABLET_PREFERENCE_COOKIE = 'orbis_ui_mode';
    const LEGACY_TABLET_PREFERENCE_COOKIE = 'orbis_tablet_mode';
    const TABLET_QUERY_PARAM = '_tablet';
    const COOKIE_MAX_AGE = 60 * 60 * 24 * 30;

    const writeTabletPreference = enabled => {
        try {
            if (enabled) localStorage.setItem(TABLET_PREFERENCE_KEY, '1');
            else localStorage.removeItem(TABLET_PREFERENCE_KEY);
        } catch (_error) {
            // Storage can be unavailable; the cookie/server session still work.
        }
        try {
            const secure = location.protocol === 'https:' ? '; Secure' : '';
            document.cookie = `${TABLET_PREFERENCE_COOKIE}=${enabled ? 'tablet' : 'desktop'}; Path=/; Max-Age=${COOKIE_MAX_AGE}; SameSite=Lax${secure}`;
            document.cookie = `${LEGACY_TABLET_PREFERENCE_COOKIE}=${enabled ? '1' : '0'}; Path=/; Max-Age=${COOKIE_MAX_AGE}; SameSite=Lax${secure}`;
        } catch (_error) {
            // UI preference only; never block navigation if cookies are disabled.
        }
    };

    // Entering any real tablet document refreshes the durable client preference.
    writeTabletPreference(true);

    const viewport = window.visualViewport || null;
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const coarsePointer = window.matchMedia('(pointer: coarse)');
    const TABLET_REFERENCE_WIDTH = 1024;
    const state = { timer: 0, lastWidth: 0, lastHeight: 0, referenceWidth: 0, keyboardOpen: false };

    const setClass = (name, enabled) => root.classList.toggle(name, Boolean(enabled));

    const usableViewport = () => {
        const layoutWidth = Math.max(320, Math.round(window.innerWidth || root.clientWidth || 0));
        const layoutHeight = Math.max(320, Math.round(window.innerHeight || root.clientHeight || 0));
        const width = Math.max(320, Math.round(viewport?.width || layoutWidth));
        const height = Math.max(280, Math.round(viewport?.height || layoutHeight));
        const top = Math.max(0, Math.round(viewport?.offsetTop || 0));
        const left = Math.max(0, Math.round(viewport?.offsetLeft || 0));
        const keyboardHeight = viewport
            ? Math.max(0, Math.round(layoutHeight - viewport.height - viewport.offsetTop))
            : 0;
        const keyboardOpen = keyboardHeight > Math.max(120, layoutHeight * 0.18);
        return { layoutWidth, layoutHeight, width, height, top, left, keyboardHeight, keyboardOpen };
    };

    const syncViewport = () => {
        const metrics = usableViewport();
        const referenceWidth = Math.min(metrics.width, TABLET_REFERENCE_WIDTH);
        state.lastWidth = metrics.width;
        state.lastHeight = metrics.height;
        state.referenceWidth = referenceWidth;
        state.keyboardOpen = metrics.keyboardOpen;

        root.classList.remove('tablet-forced-profile');
        root.classList.add('tablet-full-width-profile');
        root.style.setProperty('--tablet-reference-width', `${referenceWidth}px`);
        root.style.setProperty('--tablet-profile-reference-width', `${TABLET_REFERENCE_WIDTH}px`);
        root.style.setProperty('--tablet-vh', `${metrics.height}px`);
        root.style.setProperty('--tablet-vw', `${metrics.width}px`);
        root.style.setProperty('--tablet-layout-vh', `${metrics.layoutHeight}px`);
        root.style.setProperty('--tablet-layout-vw', `${metrics.layoutWidth}px`);
        root.style.setProperty('--tablet-viewport-top', `${metrics.top}px`);
        root.style.setProperty('--tablet-viewport-left', `${metrics.left}px`);
        root.style.setProperty('--tablet-keyboard-height', `${metrics.keyboardHeight}px`);

        const landscape = metrics.width > metrics.height;
        setClass('tablet-landscape', landscape);
        setClass('tablet-portrait', !landscape);
        setClass('tablet-compact', referenceWidth <= 820);
        setClass('tablet-wide', referenceWidth > 820);
        setClass('tablet-keyboard-open', metrics.keyboardOpen);
        setClass('tablet-coarse-pointer', coarsePointer.matches);

        if (document.body) {
            document.body.classList.add('is-tablet-shell');
            document.body.classList.toggle('is-tablet-keyboard-open', metrics.keyboardOpen);
            document.body.dataset.tablet = 'true';
            document.body.dataset.tabletOrientation = landscape ? 'landscape' : 'portrait';
            document.body.dataset.tabletWidth = String(metrics.width);
            document.body.dataset.tabletPhysicalWidth = String(metrics.width);
            document.body.dataset.tabletReferenceWidth = String(referenceWidth);
            document.body.dataset.tabletProfile = 'full-width';
            document.body.toggleAttribute('data-tablet-keyboard', metrics.keyboardOpen);
        }
    };

    const scheduleSync = (delay = 38) => {
        window.clearTimeout(state.timer);
        state.timer = window.setTimeout(syncViewport, delay);
    };

    const keepFocusedControlVisible = target => {
        if (!(target instanceof HTMLElement)) return;
        if (!target.matches('input,select,textarea,[contenteditable="true"]')) return;
        window.setTimeout(() => {
            const rect = target.getBoundingClientRect();
            const viewportHeight = viewport?.height || window.innerHeight;
            const safeTop = state.keyboardOpen ? 18 : 78;
            const safeBottom = viewportHeight - (state.keyboardOpen ? 18 : 104);
            if (rect.top < safeTop || rect.bottom > safeBottom) {
                target.scrollIntoView({
                    block: 'center',
                    inline: 'nearest',
                    behavior: reduceMotion.matches ? 'auto' : 'smooth'
                });
            }
        }, 130);
    };

    const initNavigationMotion = () => {
        const reduce = reduceMotion.matches;
        document.addEventListener('click', event => {
            const anchor = event.target instanceof Element ? event.target.closest('a[href]') : null;
            if (!anchor) return;

            const isDesktopExit = anchor.matches('.app-tablet-exit, .tablet-desktop-link')
                || /\/(?:exit-tablet|tablet\/disable)(?:[?#]|$)/.test(anchor.getAttribute('href') || '');
            if (isDesktopExit) writeTabletPreference(false);

            if (event.defaultPrevented || reduce || event.button !== 0) return;
            if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
            if (anchor.target && anchor.target !== '_self') return;
            if (anchor.hasAttribute('download') || anchor.dataset.noTabletTransition === 'true') return;

            let target;
            try { target = new URL(anchor.href, location.href); } catch (_error) { return; }
            if (target.origin !== location.origin) return;
            if (!isDesktopExit) target.searchParams.set(TABLET_QUERY_PARAM, '1');
            if (target.href === location.href || (target.pathname === location.pathname && target.search === location.search && target.hash)) return;

            // Preserve tablet context without adding a perceptible navigation delay.
            event.preventDefault();
            location.assign(target.href);
        });

        window.addEventListener('pageshow', () => root.classList.remove('tablet-navigating'), { passive: true });
    };

    const stampTabletForms = scope => {
        const rootNode = scope instanceof Element ? scope : document;
        rootNode.querySelectorAll('form').forEach(form => {
            const action = form.getAttribute('action') || location.pathname;
            if (/\/(?:exit-tablet|tablet\/disable|logout)(?:[?#]|$)/.test(action)) return;
            let marker = form.querySelector(`input[name="${TABLET_QUERY_PARAM}"][data-tablet-context]`);
            if (!marker) {
                marker = document.createElement('input');
                marker.type = 'hidden';
                marker.name = TABLET_QUERY_PARAM;
                marker.value = '1';
                marker.dataset.tabletContext = 'true';
                form.append(marker);
            }
        });
    };

    const normalizeInteractiveTables = scope => {
        const rootNode = scope instanceof Element ? scope : document;
        rootNode.querySelectorAll('table').forEach(table => {
            if (table.closest('.table-responsive,.table-wrap,[class*="table-container"],[class*="table-wrap"]')) return;
            const parent = table.parentElement;
            if (!parent || parent.dataset.tabletTableWrap === 'true') return;
            const wrapper = document.createElement('div');
            wrapper.className = 'orbis-tablet-table-wrap';
            wrapper.dataset.tabletTableWrap = 'true';
            parent.insertBefore(wrapper, table);
            wrapper.appendChild(table);
        });
    };

    const initSectionDock = () => {
        const dock = document.querySelector('.app-tablet-dock');
        const sheet = document.getElementById('tablet-section-sheet');
        const backdrop = document.getElementById('tablet-section-backdrop');
        const title = document.getElementById('tablet-section-title');
        const linksHost = document.getElementById('tablet-section-links');
        const closeButton = document.getElementById('tablet-section-close');
        if (!dock || !sheet || !backdrop || !title || !linksHost) return;

        const sectionButtons = Array.from(dock.querySelectorAll('[data-tablet-section]'));
        const sourceSections = new Map(
            Array.from(document.querySelectorAll('#app-sidebar [data-nav-section]')).map(section => [
                String(section.dataset.navSection || ''),
                section
            ])
        );

        const sourceLinks = section => Array.from(section?.querySelectorAll('a.nav-item[href]') || [])
            .filter(link => !link.hidden);

        const sectionName = section => (
            section?.querySelector('.nav-section-toggle span')?.textContent || 'Sección'
        ).trim();

        const createSheetLink = source => {
            const link = document.createElement('a');
            link.className = 'tablet-section-link';
            link.href = source.getAttribute('href') || '#';
            if (source.classList.contains('active')) {
                link.classList.add('active');
                link.setAttribute('aria-current', 'page');
            }

            const icon = document.createElement('span');
            icon.className = 'tablet-section-link-icon';
            const sourceIcon = source.querySelector('.nav-icon > svg, .nav-icon > i');
            if (sourceIcon) icon.append(sourceIcon.cloneNode(true));

            const copy = document.createElement('span');
            copy.className = 'tablet-section-link-copy';
            const strong = document.createElement('strong');
            strong.textContent = (source.querySelector('.nav-label')?.textContent || source.textContent || 'Abrir').trim();
            const small = document.createElement('small');
            small.textContent = source.classList.contains('nav-item--primary') ? 'Acción principal' : 'Abrir módulo';
            copy.append(strong, small);

            const arrow = document.createElement('span');
            arrow.className = 'tablet-section-link-arrow';
            arrow.setAttribute('aria-hidden', 'true');
            arrow.textContent = '›';
            link.append(icon, copy, arrow);
            link.addEventListener('click', closeSheet);
            return link;
        };

        const closeSheet = () => {
            root.classList.remove('tablet-section-open');
            sheet.classList.remove('open');
            backdrop.classList.remove('open');
            sheet.setAttribute('aria-hidden', 'true');
            backdrop.setAttribute('aria-hidden', 'true');
            sectionButtons.forEach(button => button.setAttribute('aria-expanded', 'false'));
        };

        const openSection = button => {
            const key = String(button.dataset.tabletSection || '');
            const section = sourceSections.get(key);
            const links = sourceLinks(section);
            if (!section || !links.length) return;

            if (sheet.classList.contains('open') && button.getAttribute('aria-expanded') === 'true') {
                closeSheet();
                return;
            }

            title.textContent = sectionName(section);
            linksHost.replaceChildren(...links.map(createSheetLink));
            sectionButtons.forEach(item => item.setAttribute('aria-expanded', String(item === button)));
            root.classList.add('tablet-section-open');
            sheet.classList.add('open');
            backdrop.classList.add('open');
            sheet.setAttribute('aria-hidden', 'false');
            backdrop.setAttribute('aria-hidden', 'false');
            sheet.querySelector('a')?.focus({preventScroll: true});
        };

        sectionButtons.forEach(button => {
            const section = sourceSections.get(String(button.dataset.tabletSection || ''));
            const links = sourceLinks(section);
            button.hidden = links.length === 0;
            if (section?.querySelector('a.nav-item.active')) {
                button.classList.add('active');
                button.setAttribute('aria-current', 'page');
            }
            button.addEventListener('click', () => openSection(button));
        });

        closeButton?.addEventListener('click', closeSheet);
        backdrop.addEventListener('click', closeSheet);
        document.addEventListener('keydown', event => {
            if (event.key === 'Escape' && sheet.classList.contains('open')) closeSheet();
        });
    };

    const init = () => {
        root.classList.add('tablet-mode-ready');
        root.classList.remove('sidebar-collapsed');
        syncViewport();
        normalizeInteractiveTables(document);
        stampTabletForms(document);
        initSectionDock();
        initNavigationMotion();

        document.addEventListener('focusin', event => keepFocusedControlVisible(event.target));
        document.addEventListener('submit', () => scheduleSync(0), true);

        if ('MutationObserver' in window) {
            const observer = new MutationObserver(records => {
                for (const record of records) {
                    for (const node of record.addedNodes) {
                        if (node instanceof Element) {
                            normalizeInteractiveTables(node);
                            stampTabletForms(node);
                        }
                    }
                }
            });
            observer.observe(document.body, { childList: true, subtree: true });
        }
    };

    window.addEventListener('resize', () => scheduleSync(), { passive: true });
    window.addEventListener('orientationchange', () => scheduleSync(120), { passive: true });
    window.addEventListener('pageshow', () => scheduleSync(0), { passive: true });
    viewport?.addEventListener('resize', () => scheduleSync(), { passive: true });
    viewport?.addEventListener('scroll', () => scheduleSync(0), { passive: true });
    coarsePointer.addEventListener?.('change', () => scheduleSync(0));

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init, { once: true });
    } else {
        init();
    }
})();
