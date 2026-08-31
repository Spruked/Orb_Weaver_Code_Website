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
ExecStart=/usr/bin/python3 $PROJECT_DIR/session_monitor/server.py
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
ExecStart=/usr/bin/npm start
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
