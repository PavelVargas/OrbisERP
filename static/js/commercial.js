(() => {
    'use strict';
    const ready = callback => document.readyState === 'loading'
        ? document.addEventListener('DOMContentLoaded', callback, { once: true })
        : callback();

    ready(() => {
        const main = document.querySelector('body > main');
        if (!main) return;

        // Keep the shell stable. Previous versions progressively translated cards and
        // whole sections with IntersectionObserver, which made normal navigation feel
        // like a bounce. Motion is now reserved for overlays/popovers only.
        main.classList.add('orbis-page');
        document.documentElement.classList.add('orbis-motion-stable');
        main.querySelectorAll('.orbis-reveal').forEach(element => element.classList.remove('orbis-reveal'));
        main.querySelectorAll('.orbis-pressed').forEach(element => element.classList.remove('orbis-pressed'));

        // Make icon-only actions understandable to keyboard and screen-reader users.
        main.querySelectorAll('a, button').forEach(control => {
            const text = control.textContent.trim();
            const title = control.getAttribute('title');
            if (!text && !control.getAttribute('aria-label') && title) control.setAttribute('aria-label', title);
        });

        // Preserve tables on small screens without forcing the whole page to overflow.
        main.querySelectorAll('table').forEach(table => {
            const parent = table.parentElement;
            if (!parent || parent.classList.contains('table-container') || parent.classList.contains('table-card')) return;
            const wrapper = document.createElement('div');
            wrapper.className = 'table-container orbis-table-wrap';
            parent.insertBefore(wrapper, table);
            wrapper.appendChild(table);
        });
    });
})();
