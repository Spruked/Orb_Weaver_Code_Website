const { app, BrowserWindow, Tray, Menu, ipcMain, screen, nativeImage, shell } = require("electron");
const { spawn, spawnSync } = require("child_process");
const path = require("path");
const fs = require("fs");
const { startWindowsDesktopBridge } = require("./wsl-desktop");

// --- Config -----------------------------------------------------------
const DEFAULT_API_BASE = "http://127.0.0.1:18441";
const DEFAULT_DASHBOARD_URL = "http://127.0.0.1:41000/session-monitor";
const DEFAULT_WORKSPACE_PATH = path.resolve(__dirname, "..");
const SETTINGS_PATH = path.join(app.getPath("userData"), "widget-settings.json");
const WIDGET_WIDTH = 360;
const WIDGET_HEIGHT = 230;
const DASHBOARD_WIDTH = 980;
const DASHBOARD_HEIGHT = 720;
const MONITOR_DIR = path.resolve(__dirname, "..", "session_monitor");
const RELEASE_MANIFEST_PATH = path.resolve(__dirname, "..", "lib", "release-manifest.ts");
const EVIDENCE_COLLECTION_INTERVAL_MS = 15000;
const WORKSPACE_SCAN_CACHE_MS = 30000;
const TOPMOST_ENFORCE_INTERVAL_MS = 2000;

app.disableHardwareAcceleration();
app.commandLine.appendSwitch("disable-gpu");

const gotSingleInstanceLock = app.requestSingleInstanceLock();
if (!gotSingleInstanceLock) {
  app.quit();
}

function loadSettings() {
  const defaults = {
    apiBase: DEFAULT_API_BASE,
    dashboardUrl: DEFAULT_DASHBOARD_URL,
    workspacePath: DEFAULT_WORKSPACE_PATH,
    pollIntervalMs: 5000,
    widgetBounds: null,
    widgetBoundsByKey: {},
    apiUsageWidget: true,
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

const widgetWindows = new Map();
let dashboardWindow = null;
let tray = null;
let desktopBridge = null;
let monitorProcess = null;
let monitorStderr = "";
let collectorTimer = null;
let topmostTimer = null;
let instanceTimer = null;
let instanceSyncPromise = null;
let widgetsHidden = false;
let settings = loadSettings();
let workspaceScanCache = null;
let workspaceScanCachedAt = 0;
let widgetSessionId = null;
let quitSaveStarted = false;
let cachedSummary = null;
let cachedSummaryAt = 0;
let summaryPromise = null;

function enforceWindowTopmost(window, level = "floating") {
  if (!window || window.isDestroyed() || !window.isVisible() || window.isMinimized()) return;
  window.setAlwaysOnTop(true, level);
}

function enforceTopmostWindows() {
  for (const { window } of widgetWindows.values()) enforceWindowTopmost(window);
  enforceWindowTopmost(dashboardWindow);
}

function startTopmostEnforcer() {
  if (topmostTimer) clearInterval(topmostTimer);
  enforceTopmostWindows();
  topmostTimer = setInterval(enforceTopmostWindows, TOPMOST_ENFORCE_INTERVAL_MS);
}

function defaultCornerBounds(slot = 0) {
  const area = screen.getPrimaryDisplay().workArea;
  const margin = 16;
  const rows = Math.max(1, Math.floor((area.height - margin) / (WIDGET_HEIGHT + margin)));
  const column = Math.floor(slot / rows);
  return {
    x: area.x + Math.max(0, area.width - (column + 1) * (WIDGET_WIDTH + margin)),
    y: area.y + Math.max(0, area.height - (slot % rows + 1) * (WIDGET_HEIGHT + margin)),
    width: WIDGET_WIDTH,
    height: WIDGET_HEIGHT,
  };
}

function widgetBounds(key, slot) {
  const bounds = settings.widgetBoundsByKey?.[key] || defaultCornerBounds(slot);
  const area = screen.getDisplayMatching(bounds).workArea;
  return {
    x: Math.min(Math.max(bounds.x, area.x), area.x + Math.max(0, area.width - WIDGET_WIDTH)),
    y: Math.min(Math.max(bounds.y, area.y), area.y + Math.max(0, area.height - WIDGET_HEIGHT)),
    width: WIDGET_WIDTH, height: WIDGET_HEIGHT,
  };
}

function instanceLabel(instance) {
  return instance?.instance_label || instance?.window_title || instance?.workspace_path || "Editor window";
}

function desktopState() {
  return {
    widgets: [...widgetWindows.values()].map(({ window, instance, title }) => ({
      id: instance.id, label: instanceLabel(instance), title, visible: window.isVisible() && !window.isMinimized(),
    })),
    dashboard: dashboardWindow && !dashboardWindow.isDestroyed() ? {
      id: "dashboard", label: "Dashboard", title: dashboardWindow.getTitle(),
      visible: dashboardWindow.isVisible() && !dashboardWindow.isMinimized(),
    } : null,
  };
}

function syncDesktop() {
  desktopBridge?.sync();
  buildTrayMenu();
}

function installTrayWindowBehavior(window) {
  window.on("close", (event) => {
    if (!quitSaveStarted) { event.preventDefault(); window.hide(); }
  });
  window.on("minimize", (event) => { event.preventDefault(); window.hide(); });
  for (const event of ["show", "restore", "ready-to-show"]) {
    window.on(event, () => { enforceWindowTopmost(window); syncDesktop(); });
  }
  window.on("hide", syncDesktop);
  window.on("page-title-updated", (event) => event.preventDefault());
}

function showWindow(window) {
  if (!window || window.isDestroyed()) return;
  if (window.isMinimized()) window.restore();
  window.show();
  enforceWindowTopmost(window);
  window.focus();
  syncDesktop();
}

function createWidgetWindow(instance) {
  const usedSlots = new Set([...widgetWindows.values()].map((entry) => entry.slot));
  let slot = 0;
  while (usedSlots.has(slot)) slot++;
  const key = instance.window_identifier || instance.id;
  const title = `Code Weaver Widget ${slot + 1} — ${instanceLabel(instance)}`;
  const window = new BrowserWindow({
    ...widgetBounds(key, slot), title,
    frame: false, transparent: true, alwaysOnTop: true, resizable: false,
    skipTaskbar: true, hasShadow: false, focusable: true, autoHideMenuBar: true,
    show: false, backgroundColor: "#00000000",
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true, nodeIntegration: false },
  });
  const entry = { window, instance, slot, key, title };
  widgetWindows.set(instance.id, entry);
  installTrayWindowBehavior(window);
  window.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  window.setMenuBarVisibility(false);
  window.loadFile(path.join(__dirname, "widget.html"));
  window.once("ready-to-show", () => { if (!widgetsHidden) window.showInactive(); });
  window.on("move", () => {
    if (window.isDestroyed()) return;
    settings = saveSettings({ widgetBoundsByKey: { ...settings.widgetBoundsByKey, [key]: window.getBounds() } });
  });
  window.on("closed", () => { widgetWindows.delete(instance.id); syncDesktop(); });
  if (settings.clickThrough) window.setIgnoreMouseEvents(true, { forward: true });
  return entry;
}

function reconcileWidgetWindows(instances) {
  const desired = instances.length ? [...instances] : [{ id: "global", instance_label: "No editor windows detected" }];
  if (settings.apiUsageWidget) desired.push({ id: "api-usage", instance_label: "API token usage" });
  const ids = new Set(desired.map((instance) => instance.id));
  for (const [id, entry] of widgetWindows) {
    if (!ids.has(id)) entry.window.destroy();
  }
  for (const instance of desired) {
    const entry = widgetWindows.get(instance.id);
    if (!entry) { createWidgetWindow(instance); continue; }
    entry.instance = instance;
    const title = `Code Weaver Widget ${entry.slot + 1} — ${instanceLabel(instance)}`;
    if (entry.title !== title) { entry.title = title; entry.window.setTitle(title); }
  }
  syncDesktop();
}

function syncInstanceWidgets() {
  if (instanceSyncPromise) return instanceSyncPromise;
  instanceSyncPromise = (async () => {
    try {
      const session = await readJson("/runtime/session");
      const result = session?.id ? await readJson(`/runtime/session/${encodeURIComponent(session.id)}/vscode-windows?active_only=true`) : { windows: [] };
      if (!Array.isArray(result.windows)) return;
      reconcileWidgetWindows(result.windows);
    } catch { /* Preserve existing windows when observation is unavailable. */ }
  })().finally(() => { instanceSyncPromise = null; });
  return instanceSyncPromise;
}

function createDashboardWindow(instanceId = "global") {
  if (dashboardWindow && !dashboardWindow.isDestroyed()) {
    showWindow(dashboardWindow);
    const select = () => dashboardWindow?.webContents.send("select-instance", instanceId);
    if (dashboardWindow.webContents.isLoading()) dashboardWindow.webContents.once("did-finish-load", select);
    else select();
    return;
  }
  dashboardWindow = new BrowserWindow({
    width: DASHBOARD_WIDTH, height: DASHBOARD_HEIGHT, minWidth: 760, minHeight: 520,
    title: "Code Weaver Dashboard", alwaysOnTop: true, skipTaskbar: true,
    autoHideMenuBar: true, backgroundColor: "#0b0f12", show: false,
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true, nodeIntegration: false },
  });
  installTrayWindowBehavior(dashboardWindow);
  dashboardWindow.setMenuBarVisibility(false);
  dashboardWindow.loadFile(path.join(__dirname, "dashboard.html"), { query: { instance: instanceId } });
  dashboardWindow.once("ready-to-show", () => showWindow(dashboardWindow));
  dashboardWindow.on("closed", () => { dashboardWindow = null; syncDesktop(); });
}

function toggleClickThrough() {
  settings = saveSettings({ clickThrough: !settings.clickThrough });
  for (const { window } of widgetWindows.values()) window.setIgnoreMouseEvents(settings.clickThrough, { forward: true });
  syncDesktop();
}

function resetWidgetPosition() {
  for (const { window, slot } of widgetWindows.values()) window.setBounds(defaultCornerBounds(slot));
}

function handleTrayAction(action, id) {
  const entry = widgetWindows.get(id);
  switch (action) {
    case "show-all":
      widgetsHidden = false;
      for (const { window } of widgetWindows.values()) showWindow(window);
      break;
    case "hide-all":
      widgetsHidden = true;
      for (const { window } of widgetWindows.values()) window.hide();
      break;
    case "toggle-widget":
      if (entry) entry.window.isVisible() ? entry.window.hide() : showWindow(entry.window);
      break;
    case "dashboard": createDashboardWindow(entry?.instance.id || "global"); break;
    case "hide-dashboard": dashboardWindow?.hide(); break;
    case "collect": void collectActiveSessionEvidence(); break;
    case "quit": app.quit(); break;
  }
  syncDesktop();
}

function buildTrayMenu() {
  if (!tray) return;
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: "Show all widgets", click: () => handleTrayAction("show-all") },
    { label: "Hide all widgets", click: () => handleTrayAction("hide-all") },
    ...[...widgetWindows.values()].map(({ instance, window }) => ({
      label: instanceLabel(instance), submenu: [
        { label: window.isVisible() ? "Hide widget" : "Show widget", click: () => handleTrayAction("toggle-widget", instance.id) },
        { label: "Open dashboard for this window", click: () => createDashboardWindow(instance.id) },
      ],
    })),
    { type: "separator" },
    { label: "Open full dashboard", click: () => createDashboardWindow() },
    { label: "Hide dashboard", click: () => dashboardWindow?.hide() },
    { label: "Open web dashboard", click: () => shell.openExternal(settings.dashboardUrl) },
    { label: "Collect evidence now", click: () => collectActiveSessionEvidence() },
    { label: "Reset widget positions", click: resetWidgetPosition },
    { label: "Click-through mode", type: "checkbox", checked: settings.clickThrough, click: toggleClickThrough },
    { type: "separator" },
    { label: "Quit Code Weaver", click: () => app.quit() },
  ]));
}

function createTray() {
  desktopBridge = startWindowsDesktopBridge(handleTrayAction, desktopState);
  if (desktopBridge) return;
  tray = new Tray(nativeImage.createFromDataURL(FALLBACK_ICON));
  tray.setToolTip("Code Weaver — widgets and dashboard");
  tray.on("click", () => handleTrayAction("show-all"));
  buildTrayMenu();
}

const FALLBACK_ICON =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAI0lEQVR42mP8z8BQz0AEYBxVSF+FMAmjChkYRhXSVyFVFAIAxa8HzGz2Z7EAAAAASUVORK5CYII=";

async function readJson(pathname) {
  const url = new URL(pathname, settings.apiBase);
  const response = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(15000) });
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

async function monitorHealth() {
  try {
    const health = await readJson("/health");
    return health?.ok === true;
  } catch {
    return false;
  }
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
  if (result.status !== 0) return null;
  return result.stdout.trimEnd();
}

function scanWorkspace(force = false) {
  const now = Date.now();
  if (!force && workspaceScanCache && now - workspaceScanCachedAt < WORKSPACE_SCAN_CACHE_MS) {
    return workspaceScanCache;
  }

  const root = settings.workspacePath;
  const ignoredDirs = new Set([".git", "node_modules", ".next", "dist", "out", "coverage", ".cache", "__pycache__"]);
  const extensionCounts = {};
  const manifests = [];
  const protectedFiles = [];
  let fileCount = 0;
  let totalBytes = 0;

  function walk(dir, depth = 0) {
    if (depth > 8 || fileCount > 5000) return;
    let entries = [];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }

    for (const entry of entries) {
      if (entry.isDirectory()) {
        if (!ignoredDirs.has(entry.name)) walk(path.join(dir, entry.name), depth + 1);
        continue;
      }
      if (!entry.isFile()) continue;

      const fullPath = path.join(dir, entry.name);
      const relativePath = path.relative(root, fullPath);
      const ext = path.extname(entry.name).toLowerCase() || "[none]";
      fileCount += 1;
      extensionCounts[ext] = (extensionCounts[ext] || 0) + 1;
      try {
        totalBytes += fs.statSync(fullPath).size;
      } catch {
        // Best-effort scan; inaccessible files are still counted by directory entry.
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
  const statusOutput = runGit(["status", "--short"]);
  const changed = statusOutput ? statusOutput.split("\n").filter(Boolean) : [];

  workspaceScanCache = {
    root,
    fileCount,
    totalBytes,
    topExtensions,
    manifests: manifests.slice(0, 12),
    protectedFiles: protectedFiles.slice(0, 16),
    changed,
    scannedAt: new Date().toISOString(),
  };
  workspaceScanCachedAt = now;
  return workspaceScanCache;
}

async function startMonitorServer() {
  if (await monitorHealth()) {
    return { ok: true, status: "already-running" };
  }

  if (!fs.existsSync(path.join(MONITOR_DIR, "server.py"))) {
    return { ok: false, error: `Missing ${path.join(MONITOR_DIR, "server.py")}` };
  }

  if (monitorProcess && !monitorProcess.killed) {
    return { ok: false, error: "Monitor process exists but API health check failed" };
  }

  monitorStderr = "";
  const env = { ...process.env };
  delete env.ELECTRON_RUN_AS_NODE;
  env.CODE_WEAVER_RUNTIME_DATA_DIR = path.join(app.getPath("home"), ".local", "share", "code-weaver-runtime");
  env.CODE_WEAVER_VAULT_PATH = path.resolve(__dirname, "..", "code_weaver_vault");
  monitorProcess = spawn("python3", ["server.py"], {
    cwd: MONITOR_DIR,
    env,
    stdio: ["ignore", "ignore", "pipe"],
    detached: false,
  });
  monitorProcess.stderr?.on("data", (chunk) => {
    monitorStderr = `${monitorStderr}${chunk.toString()}`.slice(-4000);
  });
  monitorProcess.on("exit", () => {
    monitorProcess = null;
  });

  for (let attempt = 0; attempt < 20; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 200));
    if (await monitorHealth()) {
      return { ok: true, status: "started" };
    }
  }

  return {
    ok: false,
    error: monitorStderr.trim() || "Monitor API did not become healthy on port 18441",
  };
}

async function createMonitorSession(source = "electron-dashboard") {
  try {
    const workspacePath = encodeURIComponent(settings.workspacePath);
    const session = await postJson(`/sessions?workspace_path=${workspacePath}&source=${encodeURIComponent(source)}`);
    return { ok: true, session };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
}

async function recoverStaleRuntimeSessions() {
  try {
    return {
      ok: true,
      result: await postJson("/runtime/recover-stale?reason=widget_startup_recovery"),
    };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
}

async function ensureRuntimeSession() {
  try {
    const workspacePath = encodeURIComponent(settings.workspacePath);
    const session = await postJson(`/runtime/session?workspace_path=${workspacePath}`);
    return { ok: true, session };
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

async function observeQuota(sessionId) {
  try {
    return { ok: true, result: await postJson(`/codex/quota/observe/${encodeURIComponent(sessionId)}`) };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
}

async function ingestRollout(sessionId) {
  try {
    return { ok: true, result: await postJson(`/codex/rollout/ingest/${encodeURIComponent(sessionId)}`) };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
}

async function activeSession() {
  try {
    const session = await readJson("/runtime/session");
    return session?.id ? session : null;
  } catch {
    return null;
  }
}

async function collectSessionEvidence(sessionId) {
  const [heartbeat, quota, rollout, vscode] = await Promise.allSettled([
    postJson(`/runtime/session/${encodeURIComponent(sessionId)}/heartbeat?source=electron-widget`),
    observeQuota(sessionId),
    ingestRollout(sessionId),
    scanVsCode(sessionId),
  ]);
  return {
    ok: true,
    status: "collected",
    sessionId,
    heartbeat: heartbeat.status === "fulfilled" ? heartbeat.value : { ok: false },
    quota: quota.status === "fulfilled" ? quota.value : { ok: false },
    rollout: rollout.status === "fulfilled" ? rollout.value : { ok: false },
    vscode: vscode.status === "fulfilled" ? vscode.value : { ok: false },
  };
}

async function collectActiveSessionEvidence() {
  if (!(await monitorHealth())) return { ok: false, status: "offline" };
  const session = await activeSession();
  if (!session) return { ok: true, status: "no-active-session" };

  const result = await collectSessionEvidence(session.id);
  await syncInstanceWidgets();
  return result;
}

function startEvidenceCollector() {
  if (collectorTimer) clearInterval(collectorTimer);
  collectActiveSessionEvidence();
  collectorTimer = setInterval(collectActiveSessionEvidence, EVIDENCE_COLLECTION_INTERVAL_MS);
}

async function resetSessionOnOpen() {
  await recoverStaleRuntimeSessions();
  const created = await ensureRuntimeSession();
  if (created.ok && created.session?.id) {
    widgetSessionId = created.session.id;
    await collectSessionEvidence(widgetSessionId);
  }
  return created;
}

async function saveSessionOnClose() {
  if (!(await monitorHealth())) return;
  const sessionId = widgetSessionId || (await activeSession())?.id;
  if (!sessionId) return;
  await collectSessionEvidence(sessionId);
  await endMonitorSession(sessionId);
  if (widgetSessionId === sessionId) {
    widgetSessionId = null;
  }
}

async function fetchMonitorSummary() {
  const codeCipher = readCodeCipherManifest();
  try {
    const today = await readJson("/today");
    const latestSession = (today.sessions || []).find((session) => !session.ended_at) || today.sessions?.[0] || null;
    const timelinePath = latestSession?.id
      ? `/timeline?session_id=${encodeURIComponent(latestSession.id)}&limit=80`
      : "/timeline?limit=80";
    const [quota, timeline, sources, git] = await Promise.all([
      readJson("/codex/quota"),
      readJson(timelinePath),
      readJson("/evidence/sources"),
      latestSession?.id ? readJson(`/git/${encodeURIComponent(latestSession.id)}`) : Promise.resolve(null),
    ]);
    return {
      ok: true,
      apiBase: settings.apiBase,
      workspacePath: settings.workspacePath,
      codeCipher,
      workspaceScan: scanWorkspace(false),
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
      workspaceScan: scanWorkspace(false),
      error: error instanceof Error ? error.message : String(error),
      observedAt: new Date().toISOString(),
    };
  }
}

function getMonitorSummary() {
  if (cachedSummary && Date.now() - cachedSummaryAt < 2000) return Promise.resolve(cachedSummary);
  if (summaryPromise) return summaryPromise;
  summaryPromise = fetchMonitorSummary().then((summary) => {
    cachedSummary = summary;
    cachedSummaryAt = Date.now();
    return summary;
  }).finally(() => { summaryPromise = null; });
  return summaryPromise;
}

function widgetEntryForSender(event) {
  return [...widgetWindows.values()].find(({ window }) => window.webContents === event.sender);
}

ipcMain.handle("get-widget-context", (event) => widgetEntryForSender(event)?.instance || null);
ipcMain.handle("get-api-usage", () => readJson("/api-usage/summary"));
ipcMain.handle("get-settings", () => settings);
ipcMain.handle("open-dashboard", (event) => createDashboardWindow(widgetEntryForSender(event)?.instance.id || "global"));
ipcMain.handle("get-monitor-summary", () => getMonitorSummary());
ipcMain.handle("start-monitor", () => startMonitorServer());
ipcMain.handle("collect-evidence", () => collectActiveSessionEvidence());
ipcMain.handle("observe-quota", (_event, sessionId) => observeQuota(sessionId));
ipcMain.handle("hide-widget", (event) => widgetEntryForSender(event)?.window.hide());
ipcMain.handle("quit-app", () => app.quit());
ipcMain.handle("set-workspace-path", (_event, workspacePath) => {
  if (typeof workspacePath !== "string" || workspacePath.trim().length === 0) {
    return { ok: false, error: "workspacePath is required" };
  }
  workspaceScanCache = null;
  workspaceScanCachedAt = 0;
  updateSettings({ workspacePath: workspacePath.trim() });
  return { ok: true, settings };
});
ipcMain.handle("create-session", () => createMonitorSession());
ipcMain.handle("end-session", (_event, sessionId) => endMonitorSession(sessionId));
ipcMain.handle("scan-vscode", (_event, sessionId) => scanVsCode(sessionId));
ipcMain.handle("ingest-rollout", (_event, sessionId) => ingestRollout(sessionId));
ipcMain.handle("scan-workspace", () => ({ ok: true, scan: scanWorkspace(true) }));

app.whenReady().then(async () => {
  Menu.setApplicationMenu(null);
  createTray();
  reconcileWidgetWindows([]);
  startTopmostEnforcer();
  await startMonitorServer();
  await resetSessionOnOpen();
  await syncInstanceWidgets();
  instanceTimer = setInterval(syncInstanceWidgets, 5000);
  startEvidenceCollector();
});

app.on("second-instance", () => handleTrayAction("show-all"));

app.on("before-quit", (event) => {
  if (!quitSaveStarted) {
    quitSaveStarted = true;
    desktopBridge?.stop();
    if (instanceTimer) clearInterval(instanceTimer);
    event.preventDefault();
    void saveSessionOnClose().finally(() => app.quit());
    return;
  }

  if (collectorTimer) clearInterval(collectorTimer);
  if (topmostTimer) clearInterval(topmostTimer);
  if (monitorProcess && !monitorProcess.killed) {
    monitorProcess.kill();
  }
});

app.on("window-all-closed", () => {
  // Keep running in the tray even if windows close.
});
