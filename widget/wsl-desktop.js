// WSLg has no Windows notification-area integration. Keep one native helper
// attached by pipes; it owns the Windows tray and the projected HWND styles.
const { spawn } = require('child_process');
const { createInterface } = require('readline');
const fs = require('fs');
const os = require('os');
const path = require('path');

function isWsl() {
  return process.platform === 'linux' && /microsoft/i.test(os.release());
}

function startWindowsDesktopBridge(onAction, getState) {
  const executable = '/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe';
  if (!isWsl() || !fs.existsSync(executable)) return null;
  const script = fs.readFileSync(path.join(__dirname, 'windows-tray.ps1'), 'utf8');
  let child = null;
  let restartTimer = null;
  let stopped = false;
  let retryDelay = 3000;

  function sync() {
    if (!child?.stdin?.writable || child.stdin.destroyed) return;
    child.stdin.write(`${JSON.stringify(getState())}\n`);
  }

  function launch() {
    if (stopped) return;
    child = spawn(executable, ['-NoProfile', '-NonInteractive', '-STA', '-WindowStyle', 'Hidden',
      '-EncodedCommand', Buffer.from(script, 'utf16le').toString('base64')], {
      stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true,
    });
    child.stdin.on('error', () => {}); // EOF/EPIPE during helper shutdown.
    const lines = createInterface({ input: child.stdout });
    lines.on('line', (line) => {
      try {
        const message = JSON.parse(line.replace(/^\uFEFF/, ''));
        if (message.action) onAction(message.action, message.id);
        if (message.event === 'ready') {
          retryDelay = 3000;
          console.log('[Windows desktop] Tray ready');
          sync();
        }
        if (message.event === 'windows') console.log('[Windows desktop]', JSON.stringify(message.windows));
      } catch { /* Ignore non-protocol PowerShell output. */ }
    });
    child.stderr.on('data', (chunk) => console.error('[Windows desktop]', chunk.toString().trim().slice(0,1500)));
    child.on('error', (error) => console.error('[Windows desktop]', error.message));
    child.on('close', () => {
      lines.close();
      child = null;
      if (!stopped) {
        console.error('[Windows desktop] Helper exited; retrying');
        restartTimer = setTimeout(launch, retryDelay);
        retryDelay = Math.min(retryDelay * 2, 30000);
      }
    });
    sync();
  }

  launch();
  const heartbeat = setInterval(sync, 5000);
  return {
    sync,
    stop() {
      stopped = true;
      clearInterval(heartbeat);
      clearTimeout(restartTimer);
      // The helper exits and removes its icon on EOF, or after 20s without a
      // heartbeat if Windows/WSL interop loses the pipe during a hard shutdown.
      child?.stdin?.end();
    },
  };
}

module.exports = { isWsl, startWindowsDesktopBridge };
