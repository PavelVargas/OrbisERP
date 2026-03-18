 const html = document.documentElement;
        const themeBtn = document.getElementById('themeToggle');
        const themeIcon = document.getElementById('themeIcon');
        const themeText = document.getElementById('themeText');
        
        const applyTheme = (theme) => {
            if (theme === 'light') {
                html.classList.remove('dark');
                html.setAttribute('data-theme', 'light');
                themeIcon.className = 'bi bi-moon-stars-fill';
                themeText.innerText = 'Modo Oscuro';
            } else {
                html.classList.add('dark');
                html.setAttribute('data-theme', 'dark');
                themeIcon.className = 'bi bi-sun-fill';
                themeText.innerText = 'Modo Claro';
            }
        };

        themeBtn.onclick = () => {
            const current = html.classList.contains('dark') ? 'light' : 'dark';
            localStorage.setItem('theme', current);
            applyTheme(current);
        };

        window.onload = () => {
            applyTheme(localStorage.getItem('theme') || 'dark');
        };

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