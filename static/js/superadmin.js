(() => {
    'use strict';
    const html = document.documentElement;
    const themeBtn = document.getElementById('themeToggle');
    const themeIcon = document.getElementById('themeIcon');
    const themeText = document.getElementById('themeText');

    const storedTheme = () => {
        try {
            const value = localStorage.getItem('theme') || localStorage.getItem('orbis-theme');
            if (value === 'dark' || value === 'light') return value;
        } catch (_error) {}
        return html.classList.contains('dark') || html.dataset.theme === 'dark' ? 'dark' : 'light';
    };

    const applyTheme = (theme) => {
        if (window.OrbisTheme) theme = window.OrbisTheme.set(theme);
        else {
            const dark = theme === 'dark';
            html.classList.toggle('dark', dark);
            html.dataset.theme = theme;
            html.style.colorScheme = theme;
            document.body?.classList.toggle('dark', dark);
            if (document.body) document.body.dataset.theme = theme;
            try {
                localStorage.setItem('theme', theme);
                localStorage.setItem('orbis-theme', theme);
            } catch (_error) {}
        }
        const dark = theme === 'dark';
        if (themeIcon) themeIcon.className = dark ? 'bi bi-sun-fill' : 'bi bi-moon-stars-fill';
        if (themeText) themeText.innerText = dark ? 'Modo Claro' : 'Modo Oscuro';
        return theme;
    };

    let theme = applyTheme(storedTheme());
    if (themeBtn) themeBtn.onclick = () => { theme = applyTheme(theme === 'dark' ? 'light' : 'dark'); };
    document.addEventListener('orbis:themechange', (event) => {
        theme = event.detail?.theme || storedTheme();
        applyTheme(theme);
    });

        document.getElementById('masterSearch').oninput = (e) => {
            const query = e.target.value.toLowerCase();
            document.querySelectorAll('.company-card-premium').forEach(card => {
                const searchData = (card.dataset.name + card.dataset.rnc + card.dataset.admin).toLowerCase();
                card.style.display = searchData.includes(query) ? 'flex' : 'none';
            });
        };

        // LÓGICA DEL MODAL MODIFICADA PARA PLANES
        function openMasterModal(data) {
            document.getElementById('m-name').innerText = data.name;
            document.getElementById('m-id').innerText = `#NODE-${data.id}`;
            document.getElementById('m-rnc').innerText = data.rnc || 'N/A';
            document.getElementById('m-status').innerText = data.status ? 'ONLINE' : 'OFFLINE';
            document.getElementById('m-expiry').innerText = data.expiration_date;
            
            // Actualización de Plan
            document.getElementById('m-plan').innerText = data.plan_name;
            const requestedBox = document.getElementById('m-requested-box');
            if (data.requested_plan) {
                requestedBox.style.display = 'flex';
                document.getElementById('m-requested').innerText = data.requested_plan;
            } else {
                requestedBox.style.display = 'none';
            }

            document.getElementById('m-tax').innerText = `${data.tax_name} (${data.tax_percent}%)`;
            document.getElementById('m-currency').innerText = `${data.currency_symbol} (DOP)`;
            document.getElementById('m-email').innerText = data.email || 'N/A';
            document.getElementById('m-phone').innerText = data.phone || 'N/A';
            document.getElementById('m-address').innerText = data.address || 'No registrada';

            document.getElementById('companyModal').style.display = 'flex';
        }

        function closeMasterModal() {
            document.getElementById('companyModal').style.display = 'none';
        }

        window.onclick = (e) => {
            if (e.target.id === 'companyModal') closeMasterModal();
        }
})();
