(() => {
    const getToken = () => document.querySelector('meta[name="csrf-token"]')?.content || '';
    const newOperationKey = () => window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}-${Math.random()}`;
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
        let operation = form.querySelector('input[name="_idempotency_key"]');
        if (!operation) {
            operation = document.createElement('input');
            operation.type = 'hidden';
            operation.name = '_idempotency_key';
            operation.value = newOperationKey();
            form.appendChild(operation);
        }
    };
    const nativeFetch = window.fetch.bind(window);
    window.fetch = (input, init = {}) => {
        const request = input instanceof Request ? input : null;
        const url = typeof input === 'string' ? input : input.url;
        const target = new URL(url, window.location.href);
        const method = (init.method || request?.method || 'GET').toUpperCase();
        if (target.origin === window.location.origin && !['GET', 'HEAD'].includes(method)) {
            const headers = new Headers(init.headers || request?.headers || {});
            headers.set('X-CSRF-Token', getToken());
            if (!headers.has('X-Idempotency-Key')) headers.set('X-Idempotency-Key', newOperationKey());
            init.headers = headers;
        }
        return nativeFetch(input, init);
    };
    document.addEventListener('submit', event => {
        const form = event.target;
        if (!(form instanceof HTMLFormElement) || form.dataset.allowDoubleSubmit === 'true') return;
        ensureToken(form);
        // AJAX/pseudo forms commonly prevent the native navigation themselves. Do not
        // lock their submitter for eight seconds; their own handler owns busy state.
        if (event.defaultPrevented) return;
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
