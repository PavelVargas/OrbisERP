(function () {
  'use strict';

  let feedbackBackdrop = null;
  let feedbackTrigger = null;
  let confirmBackdrop = null;
  let confirmTrigger = null;
  let confirmResolver = null;

  function sectionName() {
    const heading = document.querySelector('main h1, .workspace-header h1, .bo-header h1, .order-header h1, .ops-hero h1');
    return (heading?.textContent || document.title || 'OrbisERP').trim();
  }

  function focusableElements(root) {
    return Array.from(root.querySelectorAll(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )).filter(element => !element.hidden && element.getAttribute('aria-hidden') !== 'true');
  }

  function trapFocus(event, root) {
    if (event.key !== 'Tab') return;
    const focusable = focusableElements(root);
    if (!focusable.length) {
      event.preventDefault();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function ensureFeedback() {
    if (feedbackBackdrop) return feedbackBackdrop;
    feedbackBackdrop = document.createElement('div');
    feedbackBackdrop.className = 'orbis-feedback-backdrop';
    feedbackBackdrop.hidden = true;

    const dialog = document.createElement('section');
    dialog.className = 'orbis-feedback-dialog';
    dialog.setAttribute('role', 'alertdialog');
    dialog.setAttribute('aria-modal', 'true');
    dialog.setAttribute('aria-labelledby', 'orbisFeedbackTitle');
    dialog.setAttribute('aria-describedby', 'orbisFeedbackMessage');

    const head = document.createElement('header');
    head.className = 'orbis-feedback-head';
    const icon = document.createElement('span');
    icon.className = 'orbis-feedback-icon';
    icon.setAttribute('aria-hidden', 'true');
    const titleWrap = document.createElement('div');
    titleWrap.className = 'orbis-feedback-title';
    const context = document.createElement('small');
    context.dataset.feedbackContext = '';
    const title = document.createElement('h2');
    title.id = 'orbisFeedbackTitle';
    title.dataset.feedbackTitle = '';
    titleWrap.append(context, title);
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'orbis-feedback-close';
    close.setAttribute('aria-label', 'Cerrar');
    close.textContent = '×';
    head.append(icon, titleWrap, close);

    const body = document.createElement('div');
    body.className = 'orbis-feedback-body';
    const message = document.createElement('p');
    message.id = 'orbisFeedbackMessage';
    message.className = 'orbis-feedback-message';
    message.dataset.feedbackMessage = '';
    const detail = document.createElement('div');
    detail.className = 'orbis-feedback-detail';
    detail.dataset.feedbackDetail = '';
    detail.hidden = true;
    body.append(message, detail);

    const actions = document.createElement('footer');
    actions.className = 'orbis-feedback-actions';
    const ok = document.createElement('button');
    ok.type = 'button';
    ok.textContent = 'Entendido';
    actions.append(ok);

    dialog.append(head, body, actions);
    feedbackBackdrop.append(dialog);
    document.body.append(feedbackBackdrop);

    const hide = () => {
      feedbackBackdrop.hidden = true;
      if (feedbackTrigger && typeof feedbackTrigger.focus === 'function') feedbackTrigger.focus({preventScroll: true});
      feedbackTrigger = null;
    };
    close.addEventListener('click', hide);
    ok.addEventListener('click', hide);
    feedbackBackdrop.addEventListener('click', event => {
      if (event.target === feedbackBackdrop) hide();
    });
    feedbackBackdrop.addEventListener('keydown', event => trapFocus(event, dialog));
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && !feedbackBackdrop.hidden) hide();
    });
    return feedbackBackdrop;
  }

  function show(options) {
    options = options || {};
    const root = ensureFeedback();
    const dialog = root.querySelector('.orbis-feedback-dialog');
    const allowedTypes = new Set(['danger', 'warning', 'success', 'info']);
    const requestedType = String(options.type || 'danger').toLowerCase();
    const type = allowedTypes.has(requestedType) ? requestedType : 'danger';
    feedbackTrigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog.className = 'orbis-feedback-dialog is-' + type;
    root.querySelector('.orbis-feedback-icon').textContent = type === 'warning' ? '⚠' : type === 'success' ? '✓' : type === 'info' ? 'i' : '!';
    root.querySelector('[data-feedback-context]').textContent = options.context || sectionName();
    root.querySelector('[data-feedback-title]').textContent = options.title || (type === 'warning' ? 'Revisa esta operación' : type === 'info' ? 'Información' : 'No se pudo completar la operación');
    root.querySelector('[data-feedback-message]').textContent = options.message || 'La operación no pudo completarse.';
    const detail = root.querySelector('[data-feedback-detail]');
    detail.textContent = options.detail || '';
    detail.hidden = !options.detail;
    root.hidden = false;
    root.querySelector('.orbis-feedback-close').focus({preventScroll: true});
  }

  function ensureConfirm() {
    if (confirmBackdrop) return confirmBackdrop;
    confirmBackdrop = document.createElement('div');
    confirmBackdrop.className = 'orbis-confirm-backdrop';
    confirmBackdrop.hidden = true;

    const dialog = document.createElement('section');
    dialog.className = 'orbis-confirm-dialog';
    dialog.setAttribute('role', 'alertdialog');
    dialog.setAttribute('aria-modal', 'true');
    dialog.setAttribute('aria-labelledby', 'orbisConfirmTitle');
    dialog.setAttribute('aria-describedby', 'orbisConfirmMessage');

    const icon = document.createElement('span');
    icon.className = 'orbis-confirm-icon';
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = '!';

    const content = document.createElement('div');
    content.className = 'orbis-confirm-content';
    const context = document.createElement('small');
    context.dataset.confirmContext = '';
    const title = document.createElement('h2');
    title.id = 'orbisConfirmTitle';
    title.dataset.confirmTitle = '';
    const message = document.createElement('p');
    message.id = 'orbisConfirmMessage';
    message.dataset.confirmMessage = '';
    const detail = document.createElement('div');
    detail.className = 'orbis-confirm-detail';
    detail.dataset.confirmDetail = '';
    detail.hidden = true;
    content.append(context, title, message, detail);

    const actions = document.createElement('footer');
    actions.className = 'orbis-confirm-actions';
    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.className = 'orbis-confirm-cancel';
    cancel.textContent = 'Cancelar';
    const accept = document.createElement('button');
    accept.type = 'button';
    accept.className = 'orbis-confirm-accept';
    accept.textContent = 'Continuar';
    actions.append(cancel, accept);

    dialog.append(icon, content, actions);
    confirmBackdrop.append(dialog);
    document.body.append(confirmBackdrop);

    const finish = accepted => {
      if (confirmBackdrop.hidden) return;
      confirmBackdrop.hidden = true;
      const resolver = confirmResolver;
      confirmResolver = null;
      if (confirmTrigger && typeof confirmTrigger.focus === 'function') confirmTrigger.focus({preventScroll: true});
      confirmTrigger = null;
      if (resolver) resolver(Boolean(accepted));
    };
    cancel.addEventListener('click', () => finish(false));
    accept.addEventListener('click', () => finish(true));
    confirmBackdrop.addEventListener('click', event => {
      if (event.target === confirmBackdrop) finish(false);
    });
    confirmBackdrop.addEventListener('keydown', event => trapFocus(event, dialog));
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && !confirmBackdrop.hidden) finish(false);
    });
    return confirmBackdrop;
  }

  function ask(options) {
    options = options || {};
    const root = ensureConfirm();
    if (confirmResolver) {
      confirmResolver(false);
      confirmResolver = null;
    }
    confirmTrigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    root.querySelector('[data-confirm-context]').textContent = options.context || sectionName();
    root.querySelector('[data-confirm-title]').textContent = options.title || 'Confirma esta operación';
    root.querySelector('[data-confirm-message]').textContent = options.message || 'Esta acción modificará información del sistema.';
    const detail = root.querySelector('[data-confirm-detail]');
    detail.textContent = options.detail || '';
    detail.hidden = !options.detail;
    const accept = root.querySelector('.orbis-confirm-accept');
    accept.textContent = options.action || 'Continuar';
    accept.classList.toggle('is-danger', options.type !== 'warning' && options.type !== 'info');
    root.hidden = false;
    root.querySelector('.orbis-confirm-cancel').focus({preventScroll: true});
    return new Promise(resolve => {
      confirmResolver = resolve;
    });
  }

  function classify(el) {
    const classes = (el.className || '').toString().toLowerCase();
    const category = (el.dataset.feedbackType || '').toLowerCase();
    const source = `${classes} ${category}`;
    if (source.includes('danger') || source.includes('error')) return 'danger';
    if (source.includes('warning') || source.includes('warn')) return 'warning';
    if (source.includes('success')) return 'success';
    return 'info';
  }

  function messageText(el) {
    const explicit = (el.dataset.feedbackMessage || '').trim();
    if (explicit) return explicit;
    return (el.textContent || '').replace(/\s+/g, ' ').trim();
  }

  function scan() {
    const selectors = [
      '.workspace-alert', '.bo-alert', '.purchase-flashes .flash', '.flash-message', '.settings-alert',
      '.alert-toast', '.alert-danger', '.alert-warning', '.ops-alert.danger', '.ops-alert.warning',
      '.flash.danger', '.flash.warning', '.master-flash.danger', '.master-flash.warning',
      '.error-report'
    ];
    const seen = new Set();
    for (const el of document.querySelectorAll(selectors.join(','))) {
      if (seen.has(el)) continue;
      seen.add(el);
      const type = classify(el);
      if (type !== 'danger' && type !== 'warning') continue;
      const text = messageText(el);
      if (!text) continue;
      const requestId = el.dataset.requestId ? ` Referencia: ${el.dataset.requestId}.` : '';
      const detail = el.dataset.feedbackDetail || `Corrige la causa indicada y vuelve a intentar.${requestId} Si el problema continúa, comparte la referencia con soporte.`;
      show({
        type,
        title: el.dataset.feedbackTitle || (type === 'warning' ? 'Atención antes de continuar' : 'La operación fue rechazada'),
        message: text,
        detail
      });
      break;
    }
  }

  function bindConfirmations() {
    document.addEventListener('submit', async event => {
      const form = event.target instanceof HTMLFormElement ? event.target : null;
      if (!form || form.dataset.confirmed === 'true') return;
      const submitter = event.submitter instanceof HTMLElement ? event.submitter : null;
      const message = (
        submitter?.dataset.confirm
        || submitter?.dataset.confirmMessage
        || form.dataset.confirm
        || form.dataset.confirmMessage
        || ''
      ).trim();
      if (!message) return;

      event.preventDefault();
      event.stopImmediatePropagation();
      const source = submitter || form;
      const accepted = await ask({
        type: source.dataset.confirmType || form.dataset.confirmType || 'danger',
        context: source.dataset.confirmContext || form.dataset.confirmContext || sectionName(),
        title: source.dataset.confirmTitle || form.dataset.confirmTitle || 'Confirma esta operación',
        message,
        detail: source.dataset.confirmDetail || form.dataset.confirmDetail || 'La acción se ejecutará únicamente después de confirmar.',
        action: source.dataset.confirmAction || form.dataset.confirmAction || 'Continuar'
      });
      if (!accepted || !form.isConnected) return;

      form.dataset.confirmed = 'true';
      try {
        if (submitter && submitter.form === form) form.requestSubmit(submitter);
        else form.requestSubmit();
      } finally {
        window.setTimeout(() => { delete form.dataset.confirmed; }, 0);
      }
    }, true);
  }

  window.OrbisFeedback = Object.freeze({show});
  window.OrbisConfirm = Object.freeze({ask});
  bindConfirmations();

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', scan, {once: true});
  else scan();

  window.addEventListener('unhandledrejection', event => {
    const msg = event.reason?.message || String(event.reason || 'Error inesperado de interfaz');
    show({
      type: 'danger',
      title: 'La interfaz no pudo completar la acción',
      message: msg,
      detail: 'El error ocurrió en el navegador. La operación puede no haberse guardado; revisa el estado antes de repetirla.'
    });
  });
}());
