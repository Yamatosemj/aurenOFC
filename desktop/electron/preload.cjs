'use strict';

// API minima: renderer pode apenas solicitar ESCRITA na area de transferencia.
// Nenhuma leitura de clipboard, Node.js, sistema de arquivos ou execucao de comandos.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('aurenDesktop', Object.freeze({
  copyText: (value) => ipcRenderer.invoke('auren:copy-text', value)
}));
