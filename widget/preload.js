const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("widgetBridge", {
  getSettings: () => ipcRenderer.invoke("get-settings"),
  getMonitorSummary: () => ipcRenderer.invoke("get-monitor-summary"),
  startMonitor: () => ipcRenderer.invoke("start-monitor"),
  collectEvidence: () => ipcRenderer.invoke("collect-evidence"),
  observeQuota: (sessionId) => ipcRenderer.invoke("observe-quota", sessionId),
  setWorkspacePath: (workspacePath) => ipcRenderer.invoke("set-workspace-path", workspacePath),
  createSession: () => ipcRenderer.invoke("create-session"),
  endSession: (sessionId) => ipcRenderer.invoke("end-session", sessionId),
  scanVsCode: (sessionId) => ipcRenderer.invoke("scan-vscode", sessionId),
  ingestRollout: (sessionId) => ipcRenderer.invoke("ingest-rollout", sessionId),
  scanWorkspace: () => ipcRenderer.invoke("scan-workspace"),
  openDashboard: () => ipcRenderer.invoke("open-dashboard"),
  hideWidget: () => ipcRenderer.invoke("hide-widget"),
  quitApp: () => ipcRenderer.invoke("quit-app"),
});
