 // --- Gestión de Temas ---
    function applyThemeUI(isDark) {
        document.getElementById('themeIco').className = isDark ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
        document.getElementById('themeTxt').textContent = isDark ? 'Modo claro' : 'Modo oscuro';
    }

    let dark = (localStorage.getItem('orbis-theme') || 'dark') === 'dark';
    applyThemeUI(dark);

    document.getElementById('themeBtn').addEventListener('click', () => {
        dark = !dark;
        const theme = dark ? 'dark' : 'light';
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('orbis-theme', theme);
        applyThemeUI(dark);
    });

    // --- Modal de Inspección (Corregido y Blindado) ---
    function openModal(d) {
        // Asignación segura de textos
        document.getElementById('m-name').textContent = d.name || 'Empresa';
        document.getElementById('m-id').textContent = '#NODE-' + String(d.id || 0).padStart(3, '0');
        
        const statusEl = document.getElementById('m-status');
        statusEl.textContent = d.status ? 'Activo (Online)' : 'Suspendido (Offline)';
        statusEl.style.color = d.status ? 'var(--success)' : 'var(--danger)';

        const roEl = document.getElementById('m-readonly');
        roEl.textContent = d.is_readonly ? 'SÓLO LECTURA' : 'Acceso Total';
        roEl.style.color = d.is_readonly ? '#f39c12' : 'var(--success)';
        
        document.getElementById('m-expiry').textContent = d.expiry || 'N/A';
        document.getElementById('m-plan').textContent = d.plan || 'N/A';
        document.getElementById('m-rnc').textContent = d.rnc || 'N/A';
        document.getElementById('m-tax').textContent = (d.tax_name || 'ITBIS') + ' (' + (d.tax_percent || 0) + '%)';
        document.getElementById('m-currency').textContent = d.currency || 'N/A';
        document.getElementById('m-usage').textContent = (d.usage || 0) + ' MB';
        document.getElementById('m-email').textContent = d.email || 'N/A';
        document.getElementById('m-address').textContent = d.address || 'N/A';
        
        // Acción de formulario
        document.getElementById('renewForm').action = '/superadmin/renew_plan/' + (d.id || 0);
        
        // Mostrar
        document.getElementById('modalBg').classList.add('open');
    }
    
    function closeModal() { document.getElementById('modalBg').classList.remove('open'); }

    // --- Modal Broadcast ---
    function openBroadcastModal() { document.getElementById('broadcastModal').classList.add('open'); }
    function closeBroadcastModal() { document.getElementById('broadcastModal').classList.remove('open'); }

    // --- Buscador Inteligente ---
    document.getElementById('srch').addEventListener('input', function() {
        const t = this.value.toLowerCase();
        let count = 0;
        document.querySelectorAll('.nc').forEach(c => {
            const ok = (c.dataset.name || '').includes(t) ||
                       (c.dataset.rnc || '').includes(t) ||
                       (c.dataset.admin || '').toLowerCase().includes(t);
            c.style.display = ok ? '' : 'none';
            if (ok) count++;
        });
        document.getElementById('empty').style.display = count ? 'none' : 'block';
    });

    // --- Eventos de Cierre Global ---
    window.addEventListener('click', e => {
        if (e.target.id === 'modalBg') closeModal();
        if (e.target.id === 'broadcastModal') closeBroadcastModal();
    });