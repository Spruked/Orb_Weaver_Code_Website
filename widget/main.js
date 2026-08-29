const { app, BrowserWindow, Tray, Menu, ipcMain, screen, nativeImage, shell } = require("electron");
const { spawn, spawnSync } = require("child_process");
const path = require("path");
const fs = require("fs");

// --- Config -----------------------------------------------------------
// The monitor server runs inside WSL (session_monitor/server.py). WSL2's
// localhost forwarding should make this reachable from Windows as-is.
// If it isn't, change this to the WSL VM's IP (`wsl hostname -I`) instead.
const DEFAULT_API_BASE = "http://127.0.0.1:18441";
const DEFAULT_DASHBOARD_URL = "http://127.0.0.1:3000/session-monitor";
const DEFAULT_WORKSPACE_PATH = path.resolve(__dirname, "..");
const SETTINGS_PATH = path.join(app.getPath("userData"), "widget-settings.json");
const WIDGET_WIDTH = 360;
const WIDGET_HEIGHT = 188;
const DASHBOARD_WIDTH = 980;
const DASHBOARD_HEIGHT = 720;
const MONITOR_DIR = path.resolve(__dirname, "..", "session_monitor");
const RELEASE_MANIFEST_PATH = path.resolve(__dirname, "..", "lib", "release-manifest.ts");

app.disableHardwareAcceleration();
app.commandLine.appendSwitch("disable-gpu");

function loadSettings() {
  const defaults = {
    apiBase: DEFAULT_API_BASE,
    dashboardUrl: DEFAULT_DASHBOARD_URL,
    workspacePath: DEFAULT_WORKSPACE_PATH,
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

function updateSettings(partial) {
  settings = saveSettings(partial);
  buildTrayMenu();
  return settings;
}

let widgetWindow = null;
let dashboardWindow = null;
let tray = null;
let monitorProcess = null;
let settings = loadSettings();

function defaultCornerBounds() {
  const { workAreaSize } = screen.getPrimaryDisplay();
  const width = WIDGET_WIDTH;
  const height = WIDGET_HEIGHT;
  const margin = 16;
  return {
    x: workAreaSize.width - width - margin,
    y: workAreaSize.height - height - margin,
    width,
    height,
  };
}

function widgetBounds() {
  const bounds = settings.widgetBounds || defaultCornerBounds();
  const width = Math.max(bounds.width || WIDGET_WIDTH, WIDGET_WIDTH);
  const height = Math.max(bounds.height || WIDGET_HEIGHT, WIDGET_HEIGHT);
  const { workAreaSize } = screen.getPrimaryDisplay();
  return {
    x: Math.min(Math.max(bounds.x ?? 0, 0), Math.max(workAreaSize.width - width, 0)),
    y: Math.min(Math.max(bounds.y ?? 0, 0), Math.max(workAreaSize.height - height, 0)),
    width,
    height,
  };
}

function createWidgetWindow() {
  const bounds = widgetBounds();

  widgetWindow = new BrowserWindow({
    ...bounds,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    resizable: false,
    skipTaskbar: true,
    hasShadow: false,
    focusable: true,
    autoHideMenuBar: true,
    backgroundColor: "#00000000",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  widgetWindow.setAlwaysOnTop(true, "screen-saver");
  widgetWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  widgetWindow.setMenuBarVisibility(false);
  widgetWindow.loadFile(path.join(__dirname, "widget.html"));

  widgetWindow.on("show", () => {
    widgetWindow.setAlwaysOnTop(true, "screen-saver");
  });

  widgetWindow.on("focus", () => {
    widgetWindow.setAlwaysOnTop(true, "screen-saver");
  });

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
    width: DASHBOARD_WIDTH,
    height: DASHBOARD_HEIGHT,
    minWidth: 760,
    minHeight: 520,
    alwaysOnTop: false,
    autoHideMenuBar: true,
    backgroundColor: "#0b0f12",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  dashboardWindow.setMenuBarVisibility(false);
  dashboardWindow.loadFile(path.join(__dirname, "dashboard.html"));
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
  settings = updateSettings({ widgetBounds: bounds });
}

function buildTrayMenu() {
  if (!tray) return;
  const menu = Menu.buildFromTemplate([
    { label: "Show/Hide Widget", click: () => widgetWindow?.isVisible() ? widgetWindow.hide() : widgetWindow?.show() },
    { label: "Open Full Dashboard", click: createDashboardWindow },
    { label: "Open Web Dashboard", click: () => shell.openExternal(settings.dashboardUrl) },
    { label: "Start Monitor API", click: () => startMonitorServer() },
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
ipcMain.handle("get-monitor-summary", () => getMonitorSummary());
ipcMain.handle("start-monitor", () => startMonitorServer());
ipcMain.handle("hide-widget", () => widgetWindow?.hide());
ipcMain.handle("quit-app", () => app.quit());

app.whenReady().then(() => {
  Menu.setApplicationMenu(null);
  createTray();
  createWidgetWindow();
});

app.on("window-all-closed", () => {
  // Keep running in the tray even if windows close.
});

async function readJson(pathname) {
  const url = new URL(pathname, settings.apiBase);
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} from ${url}`);
  }
  return response.json();
}

async function postJson(pathname) {
  const url = new URL(pathname, settings.apiBase);
  const response = await fetch(url, { method: "POST" });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} from ${url}`);
  }
  return response.json();
}

function readCodeCipherManifest() {
  const fallback = {
    releaseId: "Unknown",
    version: "Unknown",
    releasedAt: "Unknown",
    repository: "Unknown",
    gitCommit: null,
    sourceManifestHash: null,
    verificationResult: "UNKNOWN",
    artifacts: [],
  };

  try {
    const text = fs.readFileSync(RELEASE_MANIFEST_PATH, "utf-8");
    const pick = (pattern) => text.match(pattern)?.[1] ?? null;
    const artifactMatches = [...text.matchAll(/\{\s*id:\s*"([^"]+)"[\s\S]*?platform:\s*"([^"]+)"[\s\S]*?filename:\s*"([^"]+)"[\s\S]*?sha256:\s*"([^"]+)"[\s\S]*?sku:\s*"([^"]+)"/g)];
    return {
      releaseId: pick(/release_id:\s*"([^"]+)"/) ?? fallback.releaseId,
      version: pick(/version:\s*"([^"]+)"/) ?? fallback.version,
      releasedAt: pick(/released_at:\s*"([^"]+)"/) ?? fallback.releasedAt,
      repository: pick(/repository:\s*"([^"]+)"/) ?? fallback.repository,
      gitCommit: pick(/git_commit:\s*"([^"]+)"/),
      sourceManifestHash: pick(/source_manifest_hash:\s*"([^"]+)"/),
      verificationResult: pick(/verification_result:\s*"([^"]+)"/) ?? fallback.verificationResult,
      artifacts: artifactMatches.map((match) => ({
        id: match[1],
        platform: match[2],
        filename: match[3],
        sha256: match[4],
        sku: match[5],
      })),
    };
  } catch {
    return fallback;
  }
}

function runGit(args) {
  const result = spawnSync("git", args, {
    cwd: settings.workspacePath,
    encoding: "utf-8",
  });
  if (result.status !== 0) {
    return null;
  }
  return result.stdout.trim();
}

function scanWorkspace() {
  const root = settings.workspacePath;
  const ignoredDirs = new Set([".git", "node_modules", ".next", "dist", "out", "coverage", ".cache"]);
  const extensionCounts = {};
  const manifests = [];
  const protectedFiles = [];
  let fileCount = 0;
  let totalBytes = 0;

  function walk(dir, depth = 0) {
    if (depth > 8 || fileCount > 5000) {
      return;
    }

    let entries = [];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }

    for (const entry of entries) {
      if (entry.isDirectory()) {
        if (!ignoredDirs.has(entry.name)) {
          walk(path.join(dir, entry.name), depth + 1);
        }
        continue;
      }

      if (!entry.isFile()) {
        continue;
      }

      const fullPath = path.join(dir, entry.name);
      const relativePath = path.relative(root, fullPath);
      const ext = path.extname(entry.name).toLowerCase() || "[none]";
      fileCount += 1;
      extensionCounts[ext] = (extensionCounts[ext] || 0) + 1;

      try {
        totalBytes += fs.statSync(fullPath).size;
      } catch {
      }

      if (/^(package-lock\.json|package\.json|schema\.prisma|next\.config\.mjs|tsconfig\.json)$/i.test(entry.name)) {
        manifests.push(relativePath);
      }
      if (/license|manifest|security|cipher|provenance/i.test(relativePath)) {
        protectedFiles.push(relativePath);
      }
    }
  }

  walk(root);

  const topExtensions = Object.entries(extensionCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([extension, count]) => ({ extension, count }));

  const changed = runGit(["status", "--short"])?.split("\n").filter(Boolean) ?? [];
  return {
    root,
    fileCount,
    totalBytes,
    topExtensions,
    manifests: manifests.slice(0, 12),
    protectedFiles: protectedFiles.slice(0, 16),
    changed,
    scannedAt: new Date().toISOString(),
  };
}

async function startMonitorServer() {
  if (monitorProcess && !monitorProcess.killed) {
    return { ok: true, status: "already-running" };
  }

  if (!fs.existsSync(path.join(MONITOR_DIR, "server.py"))) {
    return { ok: false, error: `Missing ${path.join(MONITOR_DIR, "server.py")}` };
  }

  const env = { ...process.env };
  delete env.ELECTRON_RUN_AS_NODE;
  monitorProcess = spawn("python3", ["server.py"], {
    cwd: MONITOR_DIR,
    env,
    stdio: "ignore",
    detached: false,
  });
  monitorProcess.unref();
  monitorProcess.on("exit", () => {
    monitorProcess = null;
  });

  await new Promise((resolve) => setTimeout(resolve, 900));
  return { ok: true, status: "started" };
}

async function createMonitorSession() {
  try {
    const workspacePath = encodeURIComponent(settings.workspacePath);
    return { ok: true, session: await postJson(`/sessions?workspace_path=${workspacePath}&source=electron-dashboard`) };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
}

async function endMonitorSession(sessionId) {
  try {
    return { ok: true, result: await postJson(`/sessions/${encodeURIComponent(sessionId)}/end`) };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
}

async function scanVsCode(sessionId) {
  try {
    return { ok: true, result: await postJson(`/vscode/scan/${encodeURIComponent(sessionId)}`) };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
}

async function ingestRollout(sessionId) {
  try {
    return { ok: true, result: await readJson(`/codex/rollout?session_id=${encodeURIComponent(sessionId)}`) };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
}

async function getMonitorSummary() {
  const codeCipher = readCodeCipherManifest();
  try {
    const [quota, today, timeline, sources] = await Promise.all([
      readJson("/codex/quota"),
      readJson("/today"),
      readJson("/timeline?limit=80"),
      readJson("/evidence/sources"),
    ]);
    const latestSession = today.sessions?.[0];
    const git = latestSession?.id ? await readJson(`/git/${encodeURIComponent(latestSession.id)}`) : null;
    return {
      ok: true,
      apiBase: settings.apiBase,
      workspacePath: settings.workspacePath,
      codeCipher,
      workspaceScan: scanWorkspace(),
      quota,
      today,
      timeline,
      sources,
      git,
      observedAt: new Date().toISOString(),
    };
  } catch (error) {
    return {
      ok: false,
      apiBase: settings.apiBase,
      workspacePath: settings.workspacePath,
      codeCipher,
      workspaceScan: scanWorkspace(),
      error: error instanceof Error ? error.message : String(error),
      observedAt: new Date().toISOString(),
    };
  }
}

ipcMain.handle("set-workspace-path", (_event, workspacePath) => {
  if (typeof workspacePath !== "string" || workspacePath.trim().length === 0) {
    return { ok: false, error: "workspacePath is required" };
  }
  updateSettings({ workspacePath: workspacePath.trim() });
  return { ok: true, settings };
});
ipcMain.handle("create-session", () => createMonitorSession());
ipcMain.handle("end-session", (_event, sessionId) => endMonitorSession(sessionId));
ipcMain.handle("scan-vscode", (_event, sessionId) => scanVsCode(sessionId));
ipcMain.handle("ingest-rollout", (_event, sessionId) => ingestRollout(sessionId));
ipcMain.handle("scan-workspace", () => ({ ok: true, scan: scanWorkspace() }));
