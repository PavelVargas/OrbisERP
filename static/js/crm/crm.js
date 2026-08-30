(() => {
    'use strict';

    const root = document.querySelector('[data-crm-root]');
    if (!root) return;

    let activeClient = null;
    let activeCard = null;
    let requestSequence = 0;
    let clientRequest = null;
    let statusRequestInFlight = false;

    const qs = (selector, scope = root) => scope.querySelector(selector);
    const qsa = (selector, scope = root) => [...scope.querySelectorAll(selector)];
    const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, char => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[char]));
    const stageLabel = value => ({ Lead: 'Lead', Negociacion: 'Negociación', Ganado: 'Ganado', Perdido: 'Perdido' }[value] || 'Lead');
    const csrfToken = () => document.querySelector('meta[name="csrf-token"]')?.content || '';
    const operationKey = () => window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}-${Math.random().toString(16).slice(2)}`;

    function initialPayload() {
        const node = document.getElementById('crmInitialData');
        if (!node) return null;
        try {
            const value = JSON.parse(node.textContent || 'null');
            return value && typeof value === 'object' ? value : null;
        } catch (_error) {
            return null;
        }
    }

    function toast(message, error = false) {
        const element = qs('#crmToast');
        if (!element) return;
        element.textContent = message;
        element.className = `crm-toast show${error ? ' error' : ''}`;
        clearTimeout(toast.timer);
        toast.timer = setTimeout(() => element.classList.remove('show'), 2600);
    }

    async function api(url, options = {}) {
        const method = String(options.method || 'GET').toUpperCase();
        const headers = new Headers(options.headers || {});
        headers.set('Accept', 'application/json');
        if (!['GET', 'HEAD'].includes(method)) {
            const token = csrfToken();
            if (token && !headers.has('X-CSRF-Token')) headers.set('X-CSRF-Token', token);
            if (!headers.has('X-Idempotency-Key')) headers.set('X-Idempotency-Key', operationKey());
        }

        const response = await fetch(url, {
            credentials: 'same-origin',
            cache: 'no-store',
            ...options,
            method,
            headers
        });
        const contentType = response.headers.get('content-type') || '';
        let data = {};
        if (contentType.includes('application/json')) {
            data = await response.json();
        } else if (!response.ok) {
            const text = await response.text();
            if (/sesión del formulario|csrf/i.test(text)) {
                data = { message: 'La sesión de seguridad cambió. Recarga la página e inténtalo otra vez.' };
            }
        }
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
        const panels = { empty: qs('#emptyState'), error: qs('#errorState'), client: qs('#clientView') };
        Object.entries(panels).forEach(([key, panel]) => { if (panel) panel.hidden = key !== name; });
    }

    function setLoading(value) {
        const loader = qs('#loader');
        if (loader) loader.hidden = !value;
        const detail = qs('.crm-detail');
        if (detail) detail.setAttribute('aria-busy', value ? 'true' : 'false');
    }

    function updatePipeline(status) {
        qsa('#pipelineNav [data-status]').forEach(button => {
            button.classList.toggle('active', button.dataset.status === status);
            button.setAttribute('aria-pressed', String(button.dataset.status === status));
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
                <button type="button" class="crm-task-check" data-task-id="${Number(task.id)}" title="Marcar como completada" aria-label="Completar ${escapeHtml(task.title)}"><i class="bi bi-check-lg"></i></button>
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

    function setText(selector, value) {
        const element = qs(selector);
        if (element) element.textContent = value;
    }

    function fillClient(data) {
        setText('#vName', data.name || 'Cliente');
        setText('#vID', `#CLI-${String(data.id || '').padStart(4, '0')}`);
        setText('#vAvatar', (data.name || 'C').charAt(0).toUpperCase());
        setText('#vPhone', data.phone || 'Sin teléfono');
        setText('#vEmail', data.email || 'Sin correo');
        setText('#vLTV', data.ltv || 'RD$ 0.00');
        setText('#vDebtAmount', data.total_debt_format || 'RD$ 0.00');
        setText('#vDebtLabel', data.has_debt ? 'Requiere seguimiento de cobro' : 'Sin deuda pendiente');
        setText('#vAverageTicket', data.average_ticket || 'RD$ 0.00');
        const salesCount = Number(data.sales_count || 0);
        setText('#vSalesCount', `${salesCount} venta${salesCount === 1 ? '' : 's'}`);
        setText('#vLastSale', data.last_sale || 'Sin ventas');
        const pending = Number(data.pending_tasks || 0);
        setText('#vPendingTasks', `${pending} tarea${pending === 1 ? '' : 's'} pendiente${pending === 1 ? '' : 's'}`);
        const detail = qs('#vDetailLink');
        if (detail) detail.href = data.detail_url || '#';
        updatePipeline(data.status || 'Lead');
        renderTasks(Array.isArray(data.tasks) ? data.tasks : []);
        renderTimeline(Array.isArray(data.interactions) ? data.interactions : []);
    }

    async function loadClientDetails(id, element = null) {
        const clientId = Number(id);
        if (!Number.isInteger(clientId) || clientId <= 0) return;

        clientRequest?.abort();
        clientRequest = new AbortController();
        const controller = clientRequest;
        activeClient = clientId;
        activeCard = element || qs(`.crm-client-item[data-client-id="${clientId}"]`);
        qsa('.crm-client-item').forEach(card => card.classList.toggle('active', card === activeCard));
        setLoading(true);
        const sequence = ++requestSequence;
        let timedOut = false;
        const timeout = window.setTimeout(() => {
            timedOut = true;
            controller.abort();
        }, 12000);

        try {
            const data = await api(clientUrl(clientId), { signal: controller.signal });
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
            if (error?.name === 'AbortError' && !timedOut) return;
            const message = timedOut
                ? 'La ficha tardó demasiado en responder. Pulsa Reintentar.'
                : (error.message || 'No se pudo cargar la ficha.');
            setText('#errorMessage', message);
            showState('error');
            toast(message, true);
        } finally {
            window.clearTimeout(timeout);
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
            if (input) input.value = '';
            updateNoteCounter();
            await loadClientDetails(activeClient, activeCard);
            toast('Actividad registrada.');
        } catch (error) { toast(error.message, true); }
        finally { if (button) button.disabled = false; }
    }

    async function changeStatus(status) {
        if (!activeClient || statusRequestInFlight) return;
        const previous = qs('#pipelineNav [data-status].active')?.dataset.status || 'Lead';
        if (status === previous) return;
        statusRequestInFlight = true;
        qsa('#pipelineNav [data-status]').forEach(button => { button.disabled = true; });
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
        } finally {
            statusRequestInFlight = false;
            qsa('#pipelineNav [data-status]').forEach(button => { button.disabled = false; });
        }
    }

    function localDateISO() {
        const now = new Date();
        const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
        return local.toISOString().slice(0, 10);
    }

    function openTaskDialog() {
        if (!activeClient) return toast('Selecciona un cliente.', true);
        const dialog = qs('#taskModal');
        if (!dialog) return;
        const date = qs('#taskDate');
        const today = localDateISO();
        if (date) { date.min = today; date.value = today; }
        if (qs('#taskName')) qs('#taskName').value = '';
        if (qs('#taskPriority')) qs('#taskPriority').value = 'Media';
        setText('#taskError', '');
        if (typeof dialog.showModal === 'function') dialog.showModal();
        else dialog.setAttribute('open', '');
        requestAnimationFrame(() => qs('#taskName')?.focus());
    }

    function closeTaskDialog() {
        const dialog = qs('#taskModal');
        if (dialog?.open && typeof dialog.close === 'function') dialog.close();
        else dialog?.removeAttribute('open');
        setText('#taskError', '');
    }

    async function createTask(event) {
        event.preventDefault();
        if (!activeClient) return;
        const title = qs('#taskName')?.value.trim() || '';
        const dueDate = qs('#taskDate')?.value || '';
        if (!title || !dueDate) return setText('#taskError', 'Completa el asunto y la fecha.');
        const submit = event.submitter || qs('#taskForm button[type="submit"]');
        if (submit) submit.disabled = true;
        try {
            await api('/crm/api/add_task', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ client_id: activeClient, title, due_date: dueDate, priority: qs('#taskPriority')?.value || 'Media' })
            });
            closeTaskDialog();
            await loadClientDetails(activeClient, activeCard);
            toast('Tarea programada.');
        } catch (error) {
            setText('#taskError', error.message);
        } finally { if (submit) submit.disabled = false; }
    }

    async function completeTask(taskId, button = null) {
        if (button) button.disabled = true;
        try {
            await api(`/crm/api/complete_task/${Number(taskId)}`, { method: 'POST' });
            await loadClientDetails(activeClient, activeCard);
            toast('Tarea completada.');
        } catch (error) { toast(error.message, true); }
        finally { if (button?.isConnected) button.disabled = false; }
    }

    function filterClients() {
        const term = (qs('#searchClient')?.value || '').toLocaleLowerCase('es').trim();
        const stage = qs('.crm-stage-tabs button.active')?.dataset.stage || 'all';
        qsa('.crm-client-item').forEach(card => {
            const matchesText = String(card.dataset.name || '').includes(term);
            const matchesStage = stage === 'all' || card.dataset.stage === stage;
            card.hidden = !(matchesText && matchesStage);
        });
    }

    function updateNoteCounter() {
        const input = qs('#noteInput');
        const counter = qs('#noteCounter');
        if (input && counter) counter.textContent = `${input.value.length} / 2000`;
    }

    const showDirectory = () => root.classList.add('clients-open');
    const hideDirectory = () => root.classList.remove('clients-open');

    function boot() {
        qsa('.crm-client-item').forEach(card => card.addEventListener('click', () => loadClientDetails(card.dataset.clientId, card)));
        qsa('#pipelineNav [data-status]').forEach(button => button.addEventListener('click', () => changeStatus(button.dataset.status)));
        qs('#btnSave')?.addEventListener('click', saveNote);
        qs('#noteInput')?.addEventListener('input', updateNoteCounter);
        qs('#openTaskModal')?.addEventListener('click', openTaskDialog);
        qs('#taskForm')?.addEventListener('submit', createTask);
        qsa('[data-close-task]').forEach(button => button.addEventListener('click', closeTaskDialog));
        qs('#taskModal')?.addEventListener('click', event => { if (event.target === qs('#taskModal')) closeTaskDialog(); });
        qs('#taskList')?.addEventListener('click', event => {
            const button = event.target.closest('[data-task-id]');
            if (button) completeTask(button.dataset.taskId, button);
        });
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
        document.addEventListener('keydown', event => {
            if (event.key === 'Escape') {
                if (qs('#taskModal')?.open) closeTaskDialog();
                else hideDirectory();
            }
        });
        updateNoteCounter();

        const cards = qsa('.crm-client-item');
        const requested = Number(new URLSearchParams(location.search).get('client'));
        const seededId = Number(root.dataset.initialClientId || 0);
        const initial = (requested && qs(`.crm-client-item[data-client-id="${requested}"]`))
            || (seededId && qs(`.crm-client-item[data-client-id="${seededId}"]`))
            || cards[0];
        const seeded = initialPayload();

        if (initial && seeded && Number(seeded.id) === Number(initial.dataset.clientId)) {
            activeClient = Number(seeded.id);
            activeCard = initial;
            qsa('.crm-client-item').forEach(card => card.classList.toggle('active', card === activeCard));
            fillClient(seeded);
            updateCardStage(activeCard, seeded.status || 'Lead');
            showState('client');
            setLoading(false);
        } else if (initial) {
            showState('empty');
            loadClientDetails(initial.dataset.clientId, initial);
        } else {
            showState('empty');
            setLoading(false);
        }
    }

    boot();
})();
