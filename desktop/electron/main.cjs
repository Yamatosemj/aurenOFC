'use strict';

// Janela nativa para a interface Chrome EXISTENTE do Auren.
// O renderer recebe somente a pagina HTTP local; nao recebe acesso ao Node.
const { app, BrowserWindow, dialog, Menu, session } = require('electron');
const { spawn } = require('node:child_process');
const { existsSync } = require('node:fs');
const path = require('node:path');
const readline = require('node:readline');

const root = path.resolve(__dirname, '..', '..');
// O ICO da identidade visual e distribuido separadamente ate incluir assets binarios no Git.
const iconPath = path.join(__dirname, 'assets', 'auren.ico');
const URL_LINE = /^Abra: (http:\/\/127\.0\.0\.1:(\d{1,5})\/)$/;

let window = null;
let backend = null;
let starting = null;
let shutdownTimer = null;
let quitting = false;
let stopped = false;
let started = false;
let lastError = '';

const pythonCandidates = () => {
  const venv = path.join(root, '.venv', 'Scripts', 'python.exe');
  const candidates = [];
  if (existsSync(venv)) candidates.push({ command: venv, args: [] });
  if (process.platform === 'win32') candidates.push({ command: 'py', args: ['-3'] });
  candidates.push({ command: process.platform === 'win32' ? 'python' : 'python3', args: [] });
  return candidates;
};

function fatal(message) {
  if (quitting || stopped) return;
  clearTimeout(starting);
  dialog.showErrorBox('Auren Desktop', message);
  app.quit();
}

function display(url) {
  if (started || quitting) return;
  started = true;
  clearTimeout(starting);

  window = new BrowserWindow({
    title: 'Auren',
    icon: existsSync(iconPath) ? iconPath : undefined,
    width: 1200,
    height: 800,
    minWidth: 610,
    minHeight: 430,
    show: false,
    autoHideMenuBar: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
      webviewTag: false
    }
  });

  // So a pagina ja servida pelo Python pode ser exibida.
  window.webContents.on('will-navigate', (event, target) => {
    if (target !== url) event.preventDefault();
  });
  window.webContents.on('will-redirect', (event) => event.preventDefault());
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  window.webContents.on('will-attach-webview', (event) => event.preventDefault());
  window.once('ready-to-show', () => {
    if (window && !quitting) window.show();
  });
  window.on('closed', () => {
    window = null;
    app.quit();
  });
  window.loadURL(url).catch((err) => fatal('Falha ao carregar a interface local: ' + err.message));
}

function launchPython(candidates, index = 0) {
  if (quitting) return;
  if (index >= candidates.length) {
    fatal('Python nao encontrado. Instale o Python 3 ou configure a .venv do Auren.');
    return;
  }
  const candidate = candidates[index];
  const args = [
    ...candidate.args,
    '-u', '-m', 'ui.chrome_server', '--no-browser', '--desktop-stdio'
  ];
  const child = spawn(candidate.command, args, {
    cwd: root,
    windowsHide: true,
    stdio: ['pipe', 'pipe', 'pipe'],
    shell: false
  });
  backend = child;
  let spawnFailed = false;
  child.once('error', (err) => {
    spawnFailed = true;
    if (backend !== child) return;
    backend = null;
    if (err.code === 'ENOENT' && index + 1 < candidates.length) {
      launchPython(candidates, index + 1);
    } else {
      fatal('Nao foi possivel iniciar o Python: ' + err.message);
    }
  });
  child.stdout.setEncoding('utf8');
  const lines = readline.createInterface({ input: child.stdout, crlfDelay: Infinity });
  lines.on('line', (line) => {
    if (backend !== child || started || quitting) return;
    const found = URL_LINE.exec(line.trim());
    if (found && Number(found[2]) > 0 && Number(found[2]) <= 65535) display(found[1]);
  });
  child.stderr.setEncoding('utf8');
  child.stderr.on('data', (chunk) => {
    // Apenas para diagnostico de inicializacao; nunca armazena logs em disco.
    lastError = (lastError + chunk).slice(-1800);
  });
  child.once('close', (code) => {
    if (backend !== child || spawnFailed) return;
    backend = null;
    clearTimeout(shutdownTimer);
    if (quitting) {
      stopped = true;
      app.quit();
    } else {
      fatal('O servidor local do Auren encerrou (codigo ' + code + ').\n' +
        (lastError || 'Confira o ambiente Python e as dependencias instaladas.'));
    }
  });
}

function shutdown() {
  if (!backend || backend.exitCode !== null) return;
  // EOF no pipe solicita desligamento cooperativo ao servidor Python.
  if (backend.stdin && !backend.stdin.destroyed) backend.stdin.end();
  const child = backend;
  shutdownTimer = setTimeout(() => {
    // Fallback apenas se uma tarefa externa impedir o encerramento normal.
    if (backend === child) child.kill();
  }, 5000);
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (window) {
      if (window.isMinimized()) window.restore();
      window.focus();
    }
  });

  app.whenReady().then(() => {
    if (process.platform === 'win32') app.setAppUserModelId('Auren.Desktop');
    Menu.setApplicationMenu(null);
    session.defaultSession.setPermissionRequestHandler((_wc, _permission, callback) => callback(false));
    session.defaultSession.setPermissionCheckHandler(() => false);
    starting = setTimeout(() => {
      if (!started) fatal('O servidor do Auren nao iniciou. Confira Python e os pacotes instalados.');
    }, 30000);
    launchPython(pythonCandidates());
  });

  app.on('before-quit', (event) => {
    if (stopped || !backend) return;
    event.preventDefault();
    if (quitting) return;
    quitting = true;
    clearTimeout(starting);
    shutdown();
  });
  app.on('window-all-closed', () => app.quit());
}
