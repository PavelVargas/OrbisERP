(() => {
    const getToken = () => document.querySelector('meta[name="csrf-token"]')?.content || '';
    const ensureToken = form => {
        if (!(form instanceof HTMLFormElement) || (form.method || 'get').toLowerCase() !== 'post') return;
        let field = form.querySelector('input[name="_csrf_token"]');
        if (!field) {
            field = document.createElement('input');
            field.type = 'hidden';
            field.name = '_csrf_token';
            form.appendChild(field);
        }
        field.value = getToken();
    };
    const nativeFetch = window.fetch.bind(window);
    window.fetch = (input, init = {}) => {
        const url = typeof input === 'string' ? input : input.url;
        const target = new URL(url, window.location.href);
        if (target.origin === window.location.origin && !['GET', 'HEAD'].includes((init.method || 'GET').toUpperCase())) {
            const headers = new Headers(init.headers || {});
            headers.set('X-CSRF-Token', getToken());
            init.headers = headers;
        }
        return nativeFetch(input, init);
    };
    document.addEventListener('submit', event => {
        const form = event.target;
        if (!(form instanceof HTMLFormElement) || form.dataset.allowDoubleSubmit === 'true') return;
        ensureToken(form);
        const button = event.submitter;
        if (button) {
            button.disabled = true;
            button.setAttribute('aria-busy', 'true');
            setTimeout(() => { button.disabled = false; button.removeAttribute('aria-busy'); }, 8000);
        }
    });

    // form.submit() no dispara el evento submit. Varias pantallas POS crean
    // formularios de forma dinámica, por lo que protegemos también esa vía.
    const nativeSubmit = HTMLFormElement.prototype.submit;
    HTMLFormElement.prototype.submit = function secureProgrammaticSubmit() {
        ensureToken(this);
        nativeSubmit.call(this);
    };

    window.OrbisSecurity = { getCsrfToken: getToken, ensureToken };
})();
