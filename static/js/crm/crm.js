let ACTIVE_CLIENT = null;

        async function loadClientDetails(id, el) {
            ACTIVE_CLIENT = id;
            
            // UI Feedback
            document.querySelectorAll('.client-card').forEach(c => c.classList.remove('active'));
            if(el) el.classList.add('active');
            
            document.getElementById('emptyState').style.display = 'none';
            document.getElementById('clientView').style.display = 'flex';
            document.getElementById('loader').style.display = 'grid';

            try {
                const res = await fetch(`/crm/api/client/${id}`);
                const data = await res.json();

                // El símbolo viene dinámico desde el servidor
                const symbol = data.currency_symbol;

                // Renderizar Datos Básicos
                document.getElementById('vName').textContent = data.name;
                document.getElementById('vID').textContent = `#REF-${String(data.id).padStart(4, '0')}`;
                
                // El LTV ya viene con el símbolo correcto desde Python
                document.getElementById('vLTV').textContent = data.ltv;
                document.getElementById('vAvatar').textContent = data.name.charAt(0).toUpperCase();

                // Lógica de Banner de Deuda
                const banner = document.getElementById('vDebtBanner');
                if (data.has_debt) {
                    banner.style.display = 'flex';
                    // Usamos el formato convertido que viene de la API
                    document.getElementById('vDebtAmount').textContent = data.total_debt_format;
                } else {
                    banner.style.display = 'none';
                }

                // Renderizar componentes restantes
                updatePipelineUI(data.status);
                renderTasks(data.tasks);
                renderTimeline(data.interactions);

            } catch(e) {
                console.error("Error cargando CRM:", e);
            } finally {
                document.getElementById('loader').style.display = 'none';
            }
        }

        function updatePipelineUI(status) {
            document.querySelectorAll('.pipe-step').forEach(s => s.classList.remove('active'));
            const current = document.getElementById(`step-${status}`);
            if(current) current.classList.add('active');
        }

        // 3. RENDER DE TAREAS
        function renderTasks(tasks) {
            const container = document.getElementById('taskList');
            if(!tasks.length) {
                container.innerHTML = `<p style="font-size:0.8rem; color:var(--text-muted); padding:10px;">Sin tareas pendientes.</p>`;
                return;
            }
            container.innerHTML = tasks.map(t => `
                <div class="task-item" style="background: var(--bg-main); padding: 12px; border-radius: 10px; margin-bottom: 10px; border-left: 4px solid ${t.priority === 'Alta' ? '#ef4444' : 'var(--primary)'};">
                    <div style="font-weight:700; font-size:0.85rem;">${t.title}</div>
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-top:5px;">
                        <small style="color:var(--text-muted); font-weight:600;">${t.due}</small>
                        <span style="font-size: 0.6rem; background: rgba(0,0,0,0.05); padding: 2px 6px; border-radius: 4px;">${t.priority}</span>
                    </div>
                </div>
            `).join('');
        }

        // 4. RENDER DE TIMELINE
        function renderTimeline(logs) {
            const container = document.getElementById('vTimeline');
            if(!logs.length) {
                container.innerHTML = `<p style="color:var(--text-muted);">No hay actividad registrada.</p>`;
                return;
            }
            container.innerHTML = logs.map(l => `
                <div class="timeline-node">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:5px;">
                        <strong style="font-size:0.8rem; color: var(--primary);">${l.user}</strong>
                        <small style="color:var(--text-muted); font-size:0.7rem;">${l.date}</small>
                    </div>
                    <div style="font-size:0.95rem; color:var(--text-main); line-height:1.5;">${l.content}</div>
                    <div style="margin-top:8px;">
                        <span style="font-size:0.6rem; background:var(--bg-main); padding:3px 8px; border-radius:5px; text-transform:uppercase; font-weight:800; border: 1px solid var(--border);">${l.type}</span>
                    </div>
                </div>
            `).join('');
        }

        // 5. GUARDAR NOTA
        async function saveNote() {
            const text = document.getElementById('noteInput').value;
            if(!text || !ACTIVE_CLIENT) return;

            const btn = document.getElementById('btnSave');
            btn.disabled = true;
            btn.innerHTML = '<i class="bi bi-hourglass-split"></i>';

            try {
                const res = await fetch('/crm/api/add_interaction', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        client_id: ACTIVE_CLIENT,
                        content: text,
                        type: 'Nota'
                    })
                });

                if(res.ok) {
                    document.getElementById('noteInput').value = "";
                    loadClientDetails(ACTIVE_CLIENT); // Recargar timeline
                }
            } catch(e) { console.error(e); }
            finally {
                btn.disabled = false;
                btn.innerHTML = '<i class="bi bi-send-fill"></i> Registrar Nota';
            }
        }

        // 6. CAMBIO DE FASE
        async function updateStatus(newStatus) {
            if(!ACTIVE_CLIENT) return;
            updatePipelineUI(newStatus);

            await fetch('/crm/api/update_status', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    client_id: ACTIVE_CLIENT,
                    status: newStatus
                })
            });
            // Recargamos detalles para ver el log del sistema en el timeline
            loadClientDetails(ACTIVE_CLIENT);
        }

        // 7. BUSCADOR
        function filterClients() {
            const q = document.getElementById('searchClient').value.toLowerCase();
            document.querySelectorAll('.client-card').forEach(card => {
                const name = card.querySelector('div div').textContent.toLowerCase();
                card.style.display = name.includes(q) ? 'flex' : 'none';
            });
        }