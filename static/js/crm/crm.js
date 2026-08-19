let activeClient = null;
let activeCard = null;
let requestSequence = 0;

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
}[char]));

function toast(message, error = false) {
    const element = $('#crmToast');
    if (!element) return;
    element.textContent = message;
    element.className = `toast visible${error ? ' error' : ''}`;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => element.classList.remove('visible'), 2800);
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

function showPanel(name) {
    const panels = { empty: $('#emptyState'), error: $('#errorState'), client: $('#clientView') };
    Object.entries(panels).forEach(([key, panel]) => { if (panel) panel.hidden = key !== name; });
}

function clientUrl(id) {
    const base = $('.crm-page')?.dataset.clientEndpoint || '/crm/api/client/0';
    return base.replace(/\/0(?=\?|$)/, `/${Number(id)}`);
}

async function loadClientDetails(id, element = null) {
    const clientId = Number(id);
    if (!Number.isInteger(clientId) || clientId <= 0) return;
    activeClient = clientId;
    activeCard = element || $(`.client-card[data-client-id="${clientId}"]`);
    $$('.client-card').forEach((card) => card.classList.toggle('active', card === activeCard));
    showPanel('client');
    const loader = $('#loader');
    if (loader) loader.hidden = false;
    const sequence = ++requestSequence;

    try {
        const data = await api(clientUrl(clientId));
        if (sequence !== requestSequence) return;
        $('#vName').textContent = data.name || 'Cliente';
        $('#vID').textContent = `#REF-${String(data.id).padStart(4, '0')}`;
        $('#vAvatar').textContent = (data.name || 'C').charAt(0).toUpperCase();
        $('#vLTV').textContent = data.ltv || 'RD$ 0.00';
        $('#vPhone').textContent = data.phone || 'Sin teléfono';
        $('#vEmail').textContent = data.email || 'Sin correo';
        $('#vDebtBanner').hidden = !data.has_debt;
        $('#vDebtAmount').textContent = data.total_debt_format || 'RD$ 0.00';
        updatePipelineUI(data.status || 'Lead');
        renderTasks(Array.isArray(data.tasks) ? data.tasks : []);
        renderTimeline(Array.isArray(data.interactions) ? data.interactions : []);
        showPanel('client');
        $('#crmWrapper').classList.add('viewing-client');
        history.replaceState(null, '', `${location.pathname}?client=${clientId}`);
    } catch (error) {
        if (sequence !== requestSequence) return;
        $('#errorMessage').textContent = error.message;
        showPanel('error');
        toast(error.message, true);
    } finally {
        if (sequence === requestSequence && loader) loader.hidden = true;
    }
}

function updatePipelineUI(status) {
    $$('.pipeline-nav button').forEach((button) => button.classList.toggle('active', button.dataset.status === status));
}

function renderTasks(tasks) {
    $('#taskList').innerHTML = tasks.length ? tasks.map((task) => `
        <article class="task-item priority-${escapeHtml(String(task.priority || 'Media').toLowerCase())}">
            <button type="button" class="complete-task" data-task-id="${task.id}" title="Completar"><i class="bi bi-check"></i></button>
            <div><strong>${escapeHtml(task.title)}</strong><small><i class="bi bi-calendar3"></i> ${escapeHtml(task.due)}</small></div>
            <span>${escapeHtml(task.priority)}</span>
        </article>`).join('') : '<div class="inline-empty"><i class="bi bi-check2-circle"></i><p>Sin tareas pendientes</p></div>';
}

function renderTimeline(logs) {
    $('#vTimeline').innerHTML = logs.length ? logs.map((log) => {
        const icon = log.type === 'Llamada' ? 'telephone' : log.type === 'Correo' ? 'envelope' : log.type === 'Reunión' ? 'people' : 'chat-left-text';
        return `<article class="timeline-node"><span class="timeline-icon"><i class="bi bi-${icon}"></i></span><div><header><strong>${escapeHtml(log.user)}</strong><time>${escapeHtml(log.date)}</time></header><p>${escapeHtml(log.content)}</p><small>${escapeHtml(log.type)}</small></div></article>`;
    }).join('') : '<div class="inline-empty"><i class="bi bi-clock-history"></i><p>No hay actividad registrada</p></div>';
}

async function saveNote() {
    const content = $('#noteInput').value.trim();
    if (!activeClient) return toast('Selecciona un cliente.', true);
    if (!content) return toast('Escribe una nota.', true);
    const button = $('#btnSave');
    button.disabled = true;
    try {
        await api('/crm/api/add_interaction', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ client_id: activeClient, content, type: $('#noteType').value }) });
        $('#noteInput').value = '';
        await loadClientDetails(activeClient, activeCard);
        toast('Actividad registrada.');
    } catch (error) { toast(error.message, true); }
    finally { button.disabled = false; }
}

async function updateStatus(status) {
    if (!activeClient) return toast('Selecciona un cliente.', true);
    const previous = $('.pipeline-nav button.active')?.dataset.status;
    updatePipelineUI(status);
    try {
        await api('/crm/api/update_status', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ client_id: activeClient, status }) });
        if (activeCard) {
            activeCard.dataset.stage = status;
            $('.stage', activeCard).textContent = status;
        }
        await loadClientDetails(activeClient, activeCard);
        toast('Fase actualizada.');
    } catch (error) {
        updatePipelineUI(previous);
        toast(error.message, true);
    }
}

function openTaskModal() {
    if (!activeClient) return toast('Selecciona un cliente.', true);
    const today = new Date().toISOString().slice(0, 10);
    $('#taskDate').min = today;
    $('#taskDate').value = today;
    $('#taskModal').hidden = false;
    setTimeout(() => $('#taskName').focus(), 50);
}

function closeTaskModal() {
    $('#taskModal').hidden = true;
    $('#taskForm').reset();
    $('#taskError').textContent = '';
}

async function createTask(event) {
    event.preventDefault();
    try {
        await api('/crm/api/add_task', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ client_id: activeClient, title: $('#taskName').value, due_date: $('#taskDate').value, priority: $('#taskPriority').value }) });
        closeTaskModal();
        await loadClientDetails(activeClient, activeCard);
        toast('Tarea programada.');
    } catch (error) { $('#taskError').textContent = error.message; }
}

async function completeTask(id) {
    try {
        await api(`/crm/api/complete_task/${id}`, { method: 'POST' });
        await loadClientDetails(activeClient, activeCard);
        toast('Tarea completada.');
    } catch (error) { toast(error.message, true); }
}

function filterClients() {
    const term = $('#searchClient').value.toLowerCase().trim();
    const stage = $('.stage-filters .active').dataset.stage;
    $$('.client-card').forEach((card) => { card.hidden = !(card.dataset.name.includes(term) && (stage === 'all' || card.dataset.stage === stage)); });
}

function bootCRM() {
    const cards = $$('.client-card');
    cards.forEach((card) => card.addEventListener('click', () => loadClientDetails(card.dataset.clientId, card)));
    $$('.pipeline-nav button').forEach((button) => button.addEventListener('click', () => updateStatus(button.dataset.status)));
    $('#btnSave')?.addEventListener('click', saveNote);
    $('#openTaskModal')?.addEventListener('click', openTaskModal);
    $('#taskForm')?.addEventListener('submit', createTask);
    $('#retryClient')?.addEventListener('click', () => activeClient && loadClientDetails(activeClient, activeCard));
    $$('[data-close-task]').forEach((button) => button.addEventListener('click', closeTaskModal));
    $('#taskModal')?.addEventListener('click', (event) => { if (event.target === $('#taskModal')) closeTaskModal(); });
    $('#taskList')?.addEventListener('click', (event) => { const button = event.target.closest('[data-task-id]'); if (button) completeTask(button.dataset.taskId); });
    $('#searchClient')?.addEventListener('input', filterClients);
    $$('.stage-filters button').forEach((button) => button.addEventListener('click', () => {
        $$('.stage-filters button').forEach((item) => item.classList.remove('active'));
        button.classList.add('active');
        filterClients();
    }));
    $('#mobileClientsBtn')?.addEventListener('click', () => $('#crmWrapper').classList.remove('viewing-client'));
    $('#closeClients')?.addEventListener('click', () => $('#crmWrapper').classList.add('viewing-client'));
    document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && !$('#taskModal')?.hidden) closeTaskModal(); });
    const requested = Number(new URLSearchParams(location.search).get('client'));
    const initial = (requested && $(`.client-card[data-client-id="${requested}"]`)) || cards[0];
    if (initial) loadClientDetails(initial.dataset.clientId, initial);
    else showPanel('empty');
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bootCRM);
else bootCRM();
