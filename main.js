const { app, BrowserWindow, shell } = require('electron');
const path = require('path');

const APP_URL = process.env.ORBIS_URL || 'http://127.0.0.1:5000';
const APP_ORIGIN = new URL(APP_URL).origin;
let mainWindow = null;

function isTrustedAppUrl(rawUrl) {
  try {
    return new URL(rawUrl).origin === APP_ORIGIN;
  } catch (_) {
    return false;
  }
}

function safeWindowOptions() {
  return {
    nodeIntegration: false,
    contextIsolation: true,
    sandbox: true,
    webSecurity: true,
    allowRunningInsecureContent: false,
  };
}

function showOffline(win) {
  if (!win || win.isDestroyed()) return;
  win.loadFile(path.join(__dirname, 'electron_offline.html'), {
    query: { target: APP_URL },
  }).catch(() => {});
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1366,
    height: 768,
    minWidth: 1024,
    minHeight: 640,
    title: 'OrbisERP',
    backgroundColor: '#f8fafc',
    autoHideMenuBar: true,
    webPreferences: safeWindowOptions(),
  });

  win.webContents.setWindowOpenHandler(({ url }) => {
    if (isTrustedAppUrl(url)) {
      return {
        action: 'allow',
        overrideBrowserWindowOptions: {
          autoHideMenuBar: true,
          webPreferences: safeWindowOptions(),
        },
      };
    }
    if (url.startsWith('https://')) {
      shell.openExternal(url).catch(() => {});
    }
    return { action: 'deny' };
  });

  win.webContents.on('will-navigate', (event, url) => {
    if (!isTrustedAppUrl(url) && !url.startsWith('file://')) {
      event.preventDefault();
      if (url.startsWith('https://')) shell.openExternal(url).catch(() => {});
    }
  });

  win.webContents.on('did-fail-load', (_event, errorCode, _description, validatedUrl, isMainFrame) => {
    if (isMainFrame && errorCode !== -3 && isTrustedAppUrl(validatedUrl)) {
      showOffline(win);
    }
  });

  win.on('page-title-updated', (event) => event.preventDefault());
  win.on('closed', () => {
    if (mainWindow === win) mainWindow = null;
  });

  win.loadURL(APP_URL).catch(() => showOffline(win));
  mainWindow = win;
  return win;
}

const hasSingleInstanceLock = app.requestSingleInstanceLock();
if (!hasSingleInstanceLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (!mainWindow || mainWindow.isDestroyed()) {
      createWindow();
      return;
    }
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  });

  app.whenReady().then(() => {
    createWindow();
    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
  });
}

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
