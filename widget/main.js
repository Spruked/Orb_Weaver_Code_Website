const { app, BrowserWindow, Tray, Menu, ipcMain, screen, nativeImage } = require("electron");
const path = require("path");
const fs = require("fs");

// --- Config -----------------------------------------------------------
// The monitor server runs inside WSL (session_monitor/server.py). WSL2's
// localhost forwarding should make this reachable from Windows as-is.
// If it isn't, change this to the WSL VM's IP (`wsl hostname -I`) instead.
const DEFAULT_API_BASE = "http://127.0.0.1:18441";
const DEFAULT_DASHBOARD_URL = "http://127.0.0.1:3000/session-monitor";
const SETTINGS_PATH = path.join(app.getPath("userData"), "widget-settings.json");

function loadSettings() {
  const defaults = {
    apiBase: DEFAULT_API_BASE,
    dashboardUrl: DEFAULT_DASHBOARD_URL,
    pollIntervalMs: 5000,
    widgetBounds: null, // null = use default corner position
    clickThrough: false,
  };
  try {
    const raw = fs.readFileSync(SETTINGS_PATH, "utf-8");
    return { ...defaults, ...JSON.parse(raw) };
  } catch {
    return defaults;
  }
}

function saveSettings(partial) {
  const current = loadSettings();
  const next = { ...current, ...partial };
  fs.writeFileSync(SETTINGS_PATH, JSON.stringify(next, null, 2));
  return next;
}

let widgetWindow = null;
let dashboardWindow = null;
let tray = null;
let settings = loadSettings();

function defaultCornerBounds() {
  const { workAreaSize } = screen.getPrimaryDisplay();
  const width = 240;
  const height = 130;
  const margin = 16;
  return {
    x: workAreaSize.width - width - margin,
    y: workAreaSize.height - height - margin,
    width,
    height,
  };
}

function createWidgetWindow() {
  const bounds = settings.widgetBounds || defaultCornerBounds();

  widgetWindow = new BrowserWindow({
    ...bounds,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    resizable: false,
    skipTaskbar: true,
    hasShadow: false,
    focusable: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  widgetWindow.setAlwaysOnTop(true, "screen-saver");
  widgetWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  widgetWindow.loadFile(path.join(__dirname, "widget.html"));

  widgetWindow.on("move", () => {
    const [x, y] = widgetWindow.getPosition();
    const [width, height] = widgetWindow.getSize();
    settings = saveSettings({ widgetBounds: { x, y, width, height } });
  });

  if (settings.clickThrough) {
    widgetWindow.setIgnoreMouseEvents(true, { forward: true });
  }
}

function createDashboardWindow() {
  if (dashboardWindow) {
    dashboardWindow.focus();
    return;
  }
  dashboardWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: { contextIsolation: true, nodeIntegration: false },
  });
  dashboardWindow.loadURL(settings.dashboardUrl);
  dashboardWindow.on("closed", () => { dashboardWindow = null; });
}

function toggleClickThrough() {
  settings = saveSettings({ clickThrough: !settings.clickThrough });
  if (widgetWindow) {
    widgetWindow.setIgnoreMouseEvents(settings.clickThrough, { forward: true });
  }
  buildTrayMenu();
}

function resetWidgetPosition() {
  if (!widgetWindow) return;
  const bounds = defaultCornerBounds();
  widgetWindow.setBounds(bounds);
  settings = saveSettings({ widgetBounds: bounds });
}

function buildTrayMenu() {
  if (!tray) return;
  const menu = Menu.buildFromTemplate([
    { label: "Show/Hide Widget", click: () => widgetWindow?.isVisible() ? widgetWindow.hide() : widgetWindow?.show() },
    { label: "Open Full Dashboard", click: createDashboardWindow },
    { label: `API: ${settings.apiBase}`, enabled: false },
    { label: `Dashboard: ${settings.dashboardUrl}`, enabled: false },
    { label: "Reset Widget Position", click: resetWidgetPosition },
    {
      label: "Click-Through Mode",
      type: "checkbox",
      checked: settings.clickThrough,
      click: toggleClickThrough,
    },
    { type: "separator" },
    { label: "Quit", click: () => app.quit() },
  ]);
  tray.setContextMenu(menu);
}

function createTray() {
  // Simple 16x16 generated icon so this runs with zero extra asset files.
  // Swap in a real .ico/.png for a polished look later.
  const icon = nativeImage.createEmpty();
  tray = new Tray(icon.isEmpty() ? nativeImage.createFromDataURL(FALLBACK_ICON) : icon);
  tray.setToolTip("Personal Session Monitor");
  tray.on("click", () => {
    if (widgetWindow) {
      widgetWindow.isVisible() ? widgetWindow.hide() : widgetWindow.show();
    }
  });
  buildTrayMenu();
}

// 16x16 solid-color PNG as a data URL, so the tray has an icon with no
// external asset dependency. Replace with a real icon file for shipping.
const FALLBACK_ICON =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAI0lEQVR42mP8z8BQz0AEYBxVSF+FMAmjChkYRhXSVyFVFAIAxa8HzGz2Z7EAAAAASUVORK5CYII=";

ipcMain.handle("get-settings", () => settings);
ipcMain.handle("open-dashboard", () => createDashboardWindow());

app.whenReady().then(() => {
  createTray();
  createWidgetWindow();
});

app.on("window-all-closed", () => {
  // Keep running in the tray even if windows close.
});
