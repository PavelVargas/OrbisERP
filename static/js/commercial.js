(() => {
    'use strict';
    const ready = (callback) => document.readyState === 'loading'
        ? document.addEventListener('DOMContentLoaded', callback, { once: true })
        : callback();

    ready(() => {
        const main = document.querySelector('body > main');
        if (!main) return;
        main.classList.add('orbis-page');
        document.documentElement.classList.add('orbis-motion');

        const revealTargets = main.querySelectorAll([
            '.card', '.table-card', '.product-card', '.ware-card', '.kpi-card',
            '.location-panel', '.data-container', '.filter-section', '.o_form_sheet',
            '.plan-bar', '.cash-flow-control-panel', '.monthly-goals-card'
        ].join(','));
        if (!matchMedia('(prefers-reduced-motion: reduce)').matches && 'IntersectionObserver' in window) {
            const observer = new IntersectionObserver((entries) => {
                entries.forEach((entry) => {
                    if (!entry.isIntersecting) return;
                    entry.target.classList.add('orbis-revealed');
                    observer.unobserve(entry.target);
                });
            }, { rootMargin: '0px 0px -4% 0px', threshold: 0.05 });
            revealTargets.forEach((element, index) => {
                element.classList.add('orbis-reveal');
                element.style.setProperty('--reveal-delay', `${Math.min(index % 8, 7) * 34}ms`);
                observer.observe(element);
            });
        } else {
            revealTargets.forEach((element) => element.classList.add('orbis-revealed'));
        }

        // Make icon-only actions understandable to keyboard and screen-reader users.
        main.querySelectorAll('a, button').forEach((control) => {
            const text = control.textContent.trim();
            const title = control.getAttribute('title');
            if (!text && !control.getAttribute('aria-label') && title) control.setAttribute('aria-label', title);
        });

        // Preserve tables on small screens without forcing the whole page to overflow.
        main.querySelectorAll('table').forEach((table) => {
            const parent = table.parentElement;
            if (!parent || parent.classList.contains('table-container') || parent.classList.contains('table-card')) return;
            const wrapper = document.createElement('div');
            wrapper.className = 'table-container orbis-table-wrap';
            parent.insertBefore(wrapper, table);
            wrapper.appendChild(table);
        });

        // Prevent accidental double submissions in financial and inventory operations.
        main.querySelectorAll('form').forEach((form) => {
            form.addEventListener('submit', () => {
                const button = form.querySelector('button[type="submit"]');
                if (!button || button.dataset.allowMultiple === 'true') return;
                button.dataset.originalText = button.innerHTML;
                button.setAttribute('aria-busy', 'true');
                setTimeout(() => { button.disabled = true; }, 0);
            });
        });

        main.addEventListener('pointerdown', (event) => {
            const control = event.target.closest('button, .btn, [class*="btn-"], .product-card, .ware-card');
            if (!control) return;
            control.classList.add('orbis-pressed');
            const release = () => control.classList.remove('orbis-pressed');
            addEventListener('pointerup', release, { once: true });
            addEventListener('pointercancel', release, { once: true });
        });
    });
})();
