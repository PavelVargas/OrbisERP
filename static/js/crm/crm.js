(() => {
    const root = document.querySelector('[data-crm-root]');
    if (!root) return;

    let activeClient = null;
    let activeCard = null;
    let requestSequence = 0;
    const qs = (selector, scope = root) => scope.querySelector(selector);
    const qsa = (selector, scope = root) => [...scope.querySelectorAll(selector)];
    const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, char => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[char]));
    const stageLabel = value => ({ Lead: 'Lead', Negociacion: 'Negociación', Ganado: 'Ganado', Perdido: 'Perdido' }[value] || 'Lead');

    function toast(message, error = false) {
        const element = qs('#crmToast');
        if (!element) return;
        element.textContent = message;
        element.className = `crm-toast show${error ? ' error' : ''}`;
        clearTimeout(toast.timer);
        toast.timer = setTimeout(() => element.classList.remove('show'), 3000);
    }

    async function api(url, options = {}) {
        const response = await fetch(url, {
            credentials: 'same-origin',
            cache: 'no-store',
            ...options,
            headers: { Accept: 'application/json', ...(options.headers || {}) }
        });
        const contentType = response.headers.get('content-type') || '';
        const data = contentType.includes('application/json') ? await response.json() : {};
        if (!response.ok) {
            if (response.status === 401) throw new Error('Tu sesión venció. Recarga la página e inicia sesión.');
            throw new Error(data.message || data.error || 'No se pudo completar la acción.');
        }
        return data;
    }

    function clientUrl(id) {
        const base = root.dataset.clientEndpoint || '/crm/api/client/0';
        return base.replace(/\/0(?=\?|$)/, `/${Number(id)}`);
    }

    function showState(name) {
        const panels = {
            empty: qs('#emptyState'),
            error: qs('#errorState'),
            client: qs('#clientView')
        };
        Object.entries(panels).forEach(([key, panel]) => { if (panel) panel.hidden = key !== name; });
    }

    function setLoading(value) {
        const loader = qs('#loader');
        if (loader) loader.hidden = !value;
        qs('.crm-detail')?.setAttribute('aria-busy', value ? 'true' : 'false');
    }

    function updatePipeline(status) {
        qsa('#pipelineNav [data-status]').forEach(button => {
            button.classList.toggle('active', button.dataset.status === status);
        });
        const hero = qs('#vStageHero');
        if (hero) {
            hero.textContent = stageLabel(status);
            hero.className = `module-chip crm-stage-hero stage-${String(status).toLowerCase()}`;
        }
    }

    function updateCardStage(card, status) {
        if (!card) return;
        card.dataset.stage = status;
        const badge = card.querySelector('.crm-stage-badge');
        if (badge) {
            badge.textContent = stageLabel(status);
            badge.className = `crm-stage-badge stage-${String(status).toLowerCase()}`;
        }
    }

    function renderTasks(tasks) {
        const target = qs('#taskList');
        if (!target) return;
        if (!tasks.length) {
            target.innerHTML = '<div class="crm-inline-empty"><i class="bi bi-check2-circle"></i><div><strong>Sin tareas pendientes</strong><small>Este cliente está al día.</small></div></div>';
            return;
        }
        target.innerHTML = tasks.map(task => `
            <article class="crm-task-item ${task.overdue ? 'overdue' : ''}">
                <button type="button" class="crm-task-check" data-task-id="${Number(task.id)}" title="Marcar como completada"><i class="bi bi-check-lg"></i></button>
                <div class="crm-task-copy"><strong>${escapeHtml(task.title)}</strong><small><i class="bi bi-calendar3"></i> ${escapeHtml(task.due)}${task.overdue ? ' · Vencida' : ''}</small></div>
                <span class="crm-priority ${escapeHtml(String(task.priority || 'Media').toLowerCase())}">${escapeHtml(task.priority || 'Media')}</span>
            </article>`).join('');
    }

    function renderTimeline(items) {
        const target = qs('#vTimeline');
        if (!target) return;
        if (!items.length) {
            target.innerHTML = '<div class="crm-inline-empty"><i class="bi bi-clock-history"></i><div><strong>Sin actividad registrada</strong><small>Agrega una nota, llamada, correo o reunión.</small></div></div>';
            return;
        }
        const icons = { Llamada: 'telephone', Correo: 'envelope', Reunión: 'people', Sistema: 'gear', Nota: 'chat-left-text' };
        target.innerHTML = items.map(item => `
            <article class="crm-timeline-item">
                <span class="crm-timeline-avatar">${item.user_avatar ? `<img src="${escapeHtml(item.user_avatar)}" alt="">` : escapeHtml((item.user || 'S').charAt(0).toUpperCase())}</span>
                <div class="crm-timeline-copy">
                    <header><strong>${escapeHtml(item.user || 'Sistema')}</strong><span><i class="bi bi-${icons[item.type] || 'chat-left-text'}"></i> ${escapeHtml(item.type || 'Nota')} · ${escapeHtml(item.date || '')}</span></header>
                    <p>${escapeHtml(item.content || '')}</p>
                </div>
            </article>`).join('');
    }

    function fillClient(data) {
        qs('#vName').textContent = data.name || 'Cliente';
        qs('#vID').textContent = `#CLI-${String(data.id).padStart(4, '0')}`;
        qs('#vAvatar').textContent = (data.name || 'C').charAt(0).toUpperCase();
        qs('#vPhone').textContent = data.phone || 'Sin teléfono';
        qs('#vEmail').textContent = data.email || 'Sin correo';
        qs('#vLTV').textContent = data.ltv || 'RD$ 0.00';
        qs('#vDebtAmount').textContent = data.total_debt_format || 'RD$ 0.00';
        qs('#vDebtLabel').textContent = data.has_debt ? 'Requiere seguimiento de cobro' : 'Sin deuda pendiente';
        qs('#vAverageTicket').textContent = data.average_ticket || 'RD$ 0.00';
        qs('#vSalesCount').textContent = `${Number(data.sales_count || 0)} venta${Number(data.sales_count || 0) === 1 ? '' : 's'}`;
        qs('#vLastSale').textContent = data.last_sale || 'Sin ventas';
        qs('#vPendingTasks').textContent = `${Number(data.pending_tasks || 0)} tarea${Number(data.pending_tasks || 0) === 1 ? '' : 's'} pendiente${Number(data.pending_tasks || 0) === 1 ? '' : 's'}`;
        const detail = qs('#vDetailLink');
        if (detail && data.detail_url) detail.href = data.detail_url;
        updatePipeline(data.status || 'Lead');
        renderTasks(Array.isArray(data.tasks) ? data.tasks : []);
        renderTimeline(Array.isArray(data.interactions) ? data.interactions : []);
    }

    async function loadClientDetails(id, element = null) {
        const clientId = Number(id);
        if (!Number.isInteger(clientId) || clientId <= 0) return;
        activeClient = clientId;
        activeCard = element || qs(`.crm-client-item[data-client-id="${clientId}"]`);
        qsa('.crm-client-item').forEach(card => card.classList.toggle('active', card === activeCard));
        setLoading(true);
        const sequence = ++requestSequence;
        try {
            const data = await api(clientUrl(clientId));
            if (sequence !== requestSequence) return;
            fillClient(data);
            updateCardStage(activeCard, data.status || 'Lead');
            showState('client');
            root.classList.remove('clients-open');
            const url = new URL(location.href);
            url.searchParams.set('client', clientId);
            history.replaceState(null, '', url);
        } catch (error) {
            if (sequence !== requestSequence) return;
            const message = qs('#errorMessage');
            if (message) message.textContent = error.message;
            showState('error');
            toast(error.message, true);
        } finally {
            if (sequence === requestSequence) setLoading(false);
        }
    }

    async function saveNote() {
        const input = qs('#noteInput');
        const content = input?.value.trim() || '';
        if (!activeClient) return toast('Selecciona un cliente.', true);
        if (!content) return toast('Escribe una actividad antes de guardar.', true);
        const button = qs('#btnSave');
        if (button) button.disabled = true;
        try {
            await api('/crm/api/add_interaction', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ client_id: activeClient, content, type: qs('#noteType')?.value || 'Nota' })
            });
            input.value = '';
            updateNoteCounter();
            await loadClientDetails(activeClient, activeCard);
            toast('Actividad registrada.');
        } catch (error) { toast(error.message, true); }
        finally { if (button) button.disabled = false; }
    }

    async function changeStatus(status) {
        if (!activeClient) return toast('Selecciona un cliente.', true);
        const previous = qs('#pipelineNav [data-status].active')?.dataset.status || 'Lead';
        updatePipeline(status);
        try {
            const data = await api('/crm/api/update_status', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ client_id: activeClient, status })
            });
            updateCardStage(activeCard, data.status_value || status);
            await loadClientDetails(activeClient, activeCard);
            toast('Etapa comercial actualizada.');
        } catch (error) {
            updatePipeline(previous);
            toast(error.message, true);
        }
    }

    function openTaskDialog() {
        if (!activeClient) return toast('Selecciona un cliente.', true);
        const dialog = qs('#taskModal');
        if (!dialog) return;
        const date = qs('#taskDate');
        const today = new Date().toISOString().slice(0, 10);
        date.min = today;
        date.value = today;
        qs('#taskName').value = '';
        qs('#taskPriority').value = 'Media';
        qs('#taskError').textContent = '';
        dialog.showModal();
        setTimeout(() => qs('#taskName')?.focus(), 40);
    }

    function closeTaskDialog() {
        const dialog = qs('#taskModal');
        if (dialog?.open) dialog.close();
        qs('#taskError').textContent = '';
    }

    async function createTask(event) {
        event.preventDefault();
        if (!activeClient) return;
        const submit = event.submitter;
        if (submit) submit.disabled = true;
        try {
            await api('/crm/api/add_task', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    client_id: activeClient,
                    title: qs('#taskName').value.trim(),
                    due_date: qs('#taskDate').value,
                    priority: qs('#taskPriority').value
                })
            });
            closeTaskDialog();
            await loadClientDetails(activeClient, activeCard);
            toast('Tarea programada.');
        } catch (error) {
            qs('#taskError').textContent = error.message;
        } finally { if (submit) submit.disabled = false; }
    }

    async function completeTask(taskId) {
        try {
            await api(`/crm/api/complete_task/${Number(taskId)}`, { method: 'POST' });
            await loadClientDetails(activeClient, activeCard);
            toast('Tarea completada.');
        } catch (error) { toast(error.message, true); }
    }

    function filterClients() {
        const search = qs('#searchClient');
        const term = (search?.value || '').toLowerCase().trim();
        const stage = qs('.crm-stage-tabs button.active')?.dataset.stage || 'all';
        qsa('.crm-client-item').forEach(card => {
            card.hidden = !(card.dataset.name.includes(term) && (stage === 'all' || card.dataset.stage === stage));
        });
    }

    function updateNoteCounter() {
        const input = qs('#noteInput');
        const counter = qs('#noteCounter');
        if (input && counter) counter.textContent = `${input.value.length} / 2000`;
    }

    function showDirectory() {
        root.classList.add('clients-open');
    }

    function hideDirectory() {
        root.classList.remove('clients-open');
    }

    function boot() {
        qsa('.crm-client-item').forEach(card => card.addEventListener('click', () => loadClientDetails(card.dataset.clientId, card)));
        qsa('#pipelineNav [data-status]').forEach(button => button.addEventListener('click', () => changeStatus(button.dataset.status)));
        qs('#btnSave')?.addEventListener('click', saveNote);
        qs('#noteInput')?.addEventListener('input', updateNoteCounter);
        qs('#openTaskModal')?.addEventListener('click', openTaskDialog);
        qs('#taskForm')?.addEventListener('submit', createTask);
        qsa('[data-close-task]').forEach(button => button.addEventListener('click', closeTaskDialog));
        qs('#taskModal')?.addEventListener('click', event => { if (event.target === qs('#taskModal')) closeTaskDialog(); });
        qs('#taskList')?.addEventListener('click', event => { const button = event.target.closest('[data-task-id]'); if (button) completeTask(button.dataset.taskId); });
        qs('#retryClient')?.addEventListener('click', () => activeClient && loadClientDetails(activeClient, activeCard));
        qs('#searchClient')?.addEventListener('input', filterClients);
        qsa('.crm-stage-tabs button').forEach(button => button.addEventListener('click', () => {
            qsa('.crm-stage-tabs button').forEach(item => item.classList.remove('active'));
            button.classList.add('active');
            filterClients();
        }));
        document.getElementById('mobileClientsBtn')?.addEventListener('click', showDirectory);
        qs('#closeClients')?.addEventListener('click', hideDirectory);
        qs('#detailBack')?.addEventListener('click', showDirectory);
        document.addEventListener('keydown', event => { if (event.key === 'Escape' && qs('#taskModal')?.open) closeTaskDialog(); });
        updateNoteCounter();

        const cards = qsa('.crm-client-item');
        const requested = Number(new URLSearchParams(location.search).get('client'));
        const initial = (requested && qs(`.crm-client-item[data-client-id="${requested}"]`)) || cards[0];
        if (initial) loadClientDetails(initial.dataset.clientId, initial);
        else showState('empty');
    }

    boot();
})();
