const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("widgetBridge", {
  getSettings: () => ipcRenderer.invoke("get-settings"),
  openDashboard: () => ipcRenderer.invoke("open-dashboard"),
});
