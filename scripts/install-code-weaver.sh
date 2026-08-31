#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
USER_SYSTEMD_DIR="$HOME/.config/systemd/user"
USER_BIN_DIR="$HOME/.local/bin"
RUNTIME_DATA_DIR="$HOME/.local/share/code-weaver-runtime"
VAULT_DIR="$PROJECT_DIR/code_weaver_vault"
MONITOR_SERVICE="code-weaver-session-monitor.service"
WIDGET_SERVICE="code-weaver-widget.service"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_command python3
require_command curl
require_command systemctl
require_command npm

PYTHON_BIN="$(command -v python3)"
NPM_BIN="$(command -v npm)"

if ! systemctl --user show-environment >/dev/null 2>&1; then
  echo "systemd user services are not available in this WSL/user session." >&2
  echo "Enable systemd for WSL before installing Code Weaver services." >&2
  exit 1
fi

if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import fastapi
import uvicorn
PY
then
  echo "Code Weaver Python runtime dependencies are missing locally (fastapi/uvicorn)." >&2
  echo "This installer will not fetch runtime dependencies from the network." >&2
  exit 1
fi

if [ ! -f "$PROJECT_DIR/widget/package.json" ]; then
  echo "Missing widget/package.json in $PROJECT_DIR" >&2
  exit 1
fi

if [ ! -d "$PROJECT_DIR/widget/node_modules/electron" ]; then
  echo "The local Electron runtime is not present at widget/node_modules/electron." >&2
  echo "Prepare/package dependencies during the controlled build phase; runtime install will not fetch them." >&2
  exit 1
fi

mkdir -p "$USER_SYSTEMD_DIR" "$USER_BIN_DIR" "$RUNTIME_DATA_DIR"

cat >"$USER_SYSTEMD_DIR/$MONITOR_SERVICE" <<EOF
[Unit]
Description=Code Weaver Session Monitor API
After=default.target

[Service]
Type=simple
WorkingDirectory=$PROJECT_DIR/session_monitor
Environment=CODE_WEAVER_RUNTIME_DATA_DIR=$RUNTIME_DATA_DIR
Environment=CODE_WEAVER_VAULT_PATH=$VAULT_DIR
ExecStart=$PYTHON_BIN $PROJECT_DIR/session_monitor/server.py
Restart=always
RestartSec=5
StartLimitIntervalSec=60
StartLimitBurst=8
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

cat >"$USER_SYSTEMD_DIR/$WIDGET_SERVICE" <<EOF
[Unit]
Description=Code Weaver Desktop Widget
After=$MONITOR_SERVICE
Requires=$MONITOR_SERVICE

[Service]
Type=simple
WorkingDirectory=$PROJECT_DIR/widget
Environment=CODE_WEAVER_RUNTIME_DATA_DIR=$RUNTIME_DATA_DIR
Environment=CODE_WEAVER_VAULT_PATH=$VAULT_DIR
ExecStart=$NPM_BIN start
Restart=on-failure
RestartSec=5
StartLimitIntervalSec=60
StartLimitBurst=8

[Install]
WantedBy=default.target
EOF

cat >"$USER_BIN_DIR/code-weaver-code" <<EOF
#!/usr/bin/env bash
set -euo pipefail
export CODE_WEAVER_MONITOR_API="\${CODE_WEAVER_MONITOR_API:-http://127.0.0.1:18441}"
export CODE_WEAVER_WORKSPACE_PATH="\${1:-\$PWD}"
exec "$PROJECT_DIR/scripts/code-weaver-vscode-session.sh"
EOF
chmod +x "$USER_BIN_DIR/code-weaver-code"

systemctl --user daemon-reload
systemctl --user enable "$MONITOR_SERVICE" "$WIDGET_SERVICE"
systemctl --user restart "$MONITOR_SERVICE"

for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:18441/health >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

if ! curl -fsS http://127.0.0.1:18441/health >/dev/null 2>&1; then
  echo "Code Weaver monitor failed to become healthy." >&2
  systemctl --user --no-pager --full status "$MONITOR_SERVICE" || true
  exit 1
fi

systemctl --user restart "$WIDGET_SERVICE"

cat <<EOF
Code Weaver installed for this user.

Monitor:  http://127.0.0.1:18441
Runtime:  $RUNTIME_DATA_DIR
Vault:    $VAULT_DIR
Launcher: $USER_BIN_DIR/code-weaver-code

Open a tracked VS Code window with:
  code-weaver-code /path/to/workspace

Service status:
  systemctl --user status $MONITOR_SERVICE
  systemctl --user status $WIDGET_SERVICE
EOF
