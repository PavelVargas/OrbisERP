(function () {
  'use strict';
  const width = document.getElementById('receiptWidth');
  const preview = document.getElementById('receiptConfigPreview');
  const widthLabel = document.getElementById('receiptPreviewWidthLabel');
  const mode = document.getElementById('receiptPrinterMode');
  const name = document.getElementById('receiptPrinterName');
  const state = document.getElementById('receiptDeviceState');
  const pair = document.getElementById('pairReceiptPrinter');
  const printSample = document.getElementById('printReceiptSample');
  const help = document.getElementById('printerModeHelp');
  if (!width || !preview || !mode) return;

  const clampWidth = value => Math.min(112, Math.max(40, Number(value) || 80));
  function renderWidth() {
    const value = clampWidth(width.value);
    preview.style.setProperty('--receipt-preview-mm', String(value));
    if (widthLabel) widthLabel.textContent = `${value} mm`;
  }
  function setState(label, ok) {
    if (!state) return;
    state.classList.toggle('is-ok', Boolean(ok));
    state.replaceChildren();
    const icon = document.createElement('i');
    icon.className = ok ? 'bi bi-check-circle-fill' : 'bi bi-printer';
    const text = document.createElement('b');
    text.textContent = label;
    state.append(icon, text);
  }
  function storedUsb() {
    try { return JSON.parse(localStorage.getItem('orbis-receipt-usb') || 'null'); }
    catch (_error) { return null; }
  }
  function modeHelp() {
    const current = mode.value;
    if (current === 'WEBUSB') help.textContent = 'Solicita permiso a una impresora USB compatible en este navegador. El permiso queda ligado a este equipo.';
    else if (current === 'ELECTRON') help.textContent = 'Usa el cliente Orbis Desktop instalado en el equipo de caja y la impresora configurada en el sistema.';
    else help.textContent = 'El navegador abre el diálogo seguro de impresión del sistema.';
    const saved = storedUsb();
    if (current === 'WEBUSB' && saved) setState(saved.productName || 'USB vinculada', true);
    else if (name.value.trim()) setState(name.value.trim(), true);
    else setState('Sin comprobar', false);
  }

  async function pairPrinter() {
    if (mode.value === 'WEBUSB') {
      if (!navigator.usb || typeof navigator.usb.requestDevice !== 'function') {
        window.OrbisFeedback?.show({type:'warning', title:'WebUSB no disponible', message:'Este navegador no permite vincular dispositivos USB. Usa Chrome/Edge de escritorio, Orbis Desktop o el modo impresora del sistema.'});
        return;
      }
      try {
        const device = await navigator.usb.requestDevice({ filters: [] });
        const data = { vendorId: device.vendorId, productId: device.productId, productName: device.productName || `USB ${device.vendorId}:${device.productId}` };
        localStorage.setItem('orbis-receipt-usb', JSON.stringify(data));
        name.value = data.productName;
        setState(data.productName, true);
        window.OrbisFeedback?.show({type:'success', title:'Dispositivo vinculado', message:`${data.productName} quedó autorizado en este equipo. Guarda la configuración para identificarlo dentro de OrbisERP.`});
      } catch (error) {
        if (error && error.name === 'NotFoundError') return;
        window.OrbisFeedback?.show({type:'danger', title:'No se pudo vincular la impresora', message:error?.message || 'El navegador rechazó la conexión USB.'});
      }
      return;
    }
    if (mode.value === 'ELECTRON') {
      name.focus();
      setState(name.value.trim() || 'Orbis Desktop', Boolean(name.value.trim()));
      window.OrbisFeedback?.show({type:'info', title:'Impresora de Orbis Desktop', message:'Escribe el nombre con el que el sistema operativo reconoce la impresora. La selección física se administra en el equipo donde está instalado Orbis Desktop.'});
      return;
    }
    setState(name.value.trim() || 'Impresora del sistema', true);
    window.OrbisFeedback?.show({type:'info', title:'Impresora del sistema', message:'La conexión se valida al imprimir: el navegador mostrará las impresoras instaladas y recordará la preferencia según las políticas del sistema operativo.'});
  }

  width.addEventListener('input', renderWidth);
  width.addEventListener('change', () => { width.value = String(clampWidth(width.value)); renderWidth(); });
  document.querySelectorAll('[data-receipt-width]').forEach(button => button.addEventListener('click', () => {
    width.value = button.dataset.receiptWidth;
    renderWidth();
  }));
  mode.addEventListener('change', modeHelp);
  name.addEventListener('input', modeHelp);
  pair?.addEventListener('click', pairPrinter);
  printSample?.addEventListener('click', () => {
    document.body.classList.add('receipt-config-printing');
    const cleanup = () => document.body.classList.remove('receipt-config-printing');
    window.addEventListener('afterprint', cleanup, {once:true});
    window.print();
    setTimeout(cleanup, 1500);
  });
  renderWidth();
  modeHelp();
}());
