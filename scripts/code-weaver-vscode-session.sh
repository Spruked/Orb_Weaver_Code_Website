#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/bryan/projects/Orb_Weaver_Code_Website"
MONITOR_DIR="$PROJECT_DIR/session_monitor"
API_BASE="${CODE_WEAVER_MONITOR_API:-http://127.0.0.1:18441}"
WORKSPACE_PATH="${CODE_WEAVER_WORKSPACE_PATH:-$PROJECT_DIR}"
RUNTIME_SESSION_ID=""
WINDOW_ID=""

urlencode() {
  python3 - "$1" <<'PY'
import sys
from urllib.parse import quote
print(quote(sys.argv[1], safe=""))
PY
}

monitor_online() {
  curl -fsS "$API_BASE/health" >/dev/null 2>&1
}

start_monitor_if_needed() {
  if monitor_online; then
    return
  fi
  (
    cd "$MONITOR_DIR"
    CODE_WEAVER_RUNTIME_DATA_DIR="$HOME/.local/share/code-weaver-runtime" \
      CODE_WEAVER_VAULT_PATH="$PROJECT_DIR/code_weaver_vault" \
      python3 server.py
  ) >/dev/null 2>&1 &
  disown || true
  for _ in $(seq 1 30); do
    if monitor_online; then
      return
    fi
    sleep 0.5
  done
  echo "Code Weaver monitor did not become healthy at $API_BASE" >&2
  exit 1
}

end_session() {
  if [ -n "$WINDOW_ID" ]; then
    curl -fsS -X POST "$API_BASE/runtime/vscode-windows/$WINDOW_ID/close?reason=vscode_window_closed" >/dev/null 2>&1 || true
  fi
}

trap end_session EXIT INT TERM

start_monitor_if_needed
workspace="$(urlencode "$WORKSPACE_PATH")"
RUNTIME_SESSION_ID="$(
  curl -fsS -X POST "$API_BASE/runtime/session?workspace_path=$workspace" |
    python3 -c 'import json,sys; print(json.load(sys.stdin).get("id", ""))'
)"
WINDOW_IDENTITY="$(hostname 2>/dev/null || echo unknown)-$$-$(date +%s)"
WINDOW_ID="$(
  curl -fsS -X POST "$API_BASE/runtime/session/$RUNTIME_SESSION_ID/vscode-windows?workspace_path=$workspace&source=vscode_folder_open&process_id=$$&window_identifier=$WINDOW_IDENTITY&focus_state=unknown" |
    python3 -c 'import json,sys; print(json.load(sys.stdin).get("id", ""))'
)"

if command -v code >/dev/null 2>&1; then
  code -n --wait "$WORKSPACE_PATH"
else
  echo "VS Code command 'code' was not found in PATH." >&2
  exit 127
fi
