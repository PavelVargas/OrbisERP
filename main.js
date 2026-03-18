const { app, BrowserWindow } = require('electron');
const path = require('path');

function createWindow() {
  const win = new BrowserWindow({
    width: 1366,
    height: 768,
    title: "OrbisERP",
    // Para que la app se vea nativa desde el inicio
    backgroundColor: '#f8fafc', 
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true
    }
  });

  // Carga la URL de tu servidor Flask
  win.loadURL('http://127.0.0.1:5000');

  // Opcional: Descomenta la línea de abajo para ocultar el menú (File, Edit...)
  // win.setMenuBarVisibility(false);

  // Manejo de títulos dinámicos para que siempre diga OrbisERP
  win.on('page-title-updated', (e) => e.preventDefault());
}

app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});