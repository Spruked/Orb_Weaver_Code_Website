#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MONITOR_DIR="$PROJECT_DIR/session_monitor"
API_BASE="${CODE_WEAVER_MONITOR_API:-http://127.0.0.1:18441}"
WORKSPACE_PATH="${CODE_WEAVER_WORKSPACE_PATH:-${1:-$PWD}}"
VSCODE_LOG_ROOT="$HOME/.vscode-server/data/logs"
RUNTIME_SESSION_ID=""
WINDOW_ID=""
CODE_PID=""
BEFORE_LOGS=""

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

close_window_record() {
  if [ -n "$WINDOW_ID" ]; then
    curl -fsS -X POST \
      "$API_BASE/runtime/vscode-windows/$WINDOW_ID/close?reason=vscode_window_closed" \
      >/dev/null 2>&1 || true
  fi
  if [ -n "$BEFORE_LOGS" ] && [ -f "$BEFORE_LOGS" ]; then
    rm -f "$BEFORE_LOGS"
  fi
}

snapshot_log_dirs() {
  if [ -d "$VSCODE_LOG_ROOT" ]; then
    find "$VSCODE_LOG_ROOT" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null | sort
  fi
}

try_bind_new_log_dir() {
  [ -n "$WINDOW_ID" ] || return 0
  [ -d "$VSCODE_LOG_ROOT" ] || return 0
  [ -n "$BEFORE_LOGS" ] || return 0

  local current_file new_file count selected encoded
  current_file="$(mktemp)"
  new_file="$(mktemp)"
  snapshot_log_dirs >"$current_file"
  comm -13 "$BEFORE_LOGS" "$current_file" >"$new_file" || true
  count="$(grep -c . "$new_file" 2>/dev/null || true)"

  if [ "$count" = "1" ]; then
    selected="$(head -n 1 "$new_file")"
    encoded="$(urlencode "$VSCODE_LOG_ROOT/$selected")"
    curl -fsS -X POST \
      "$API_BASE/runtime/vscode-windows/$WINDOW_ID/bind-log?log_session_dir=$encoded&evidence_class=derived" \
      >/dev/null 2>&1 || true
    rm -f "$current_file" "$new_file"
    return 0
  fi

  rm -f "$current_file" "$new_file"
  return 1
}

trap close_window_record EXIT INT TERM

start_monitor_if_needed
workspace="$(urlencode "$WORKSPACE_PATH")"
RUNTIME_SESSION_ID="$(
  curl -fsS -X POST "$API_BASE/runtime/session?workspace_path=$workspace" |
    python3 -c 'import json,sys; print(json.load(sys.stdin).get("id", ""))'
)"

if [ -z "$RUNTIME_SESSION_ID" ]; then
  echo "Code Weaver runtime session was not created." >&2
  exit 1
fi

WINDOW_IDENTITY="$(hostname 2>/dev/null || echo unknown)-$$-$(date +%s%N)"
WINDOW_ID="$(
  curl -fsS -X POST \
    "$API_BASE/runtime/session/$RUNTIME_SESSION_ID/vscode-windows?workspace_path=$workspace&source=vscode_folder_open&process_id=$$&window_identifier=$WINDOW_IDENTITY&focus_state=unknown" |
    python3 -c 'import json,sys; print(json.load(sys.stdin).get("id", ""))'
)"

if [ -z "$WINDOW_ID" ]; then
  echo "Code Weaver could not register the VS Code child window." >&2
  exit 1
fi

if ! command -v code >/dev/null 2>&1; then
  echo "VS Code command 'code' was not found in PATH." >&2
  exit 127
fi

BEFORE_LOGS="$(mktemp)"
snapshot_log_dirs >"$BEFORE_LOGS"

code -n --wait "$WORKSPACE_PATH" &
CODE_PID=$!

# A unique new VS Code log-session directory is a strong temporal association,
# but not a documented authoritative window ID, so it is recorded as DERIVED.
for _ in $(seq 1 40); do
  if try_bind_new_log_dir; then
    break
  fi
  if ! kill -0 "$CODE_PID" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

# Trigger a scan so the dashboard tab appears promptly even when log binding
# remains ambiguous and must stay INFERRED.
curl -fsS -X POST "$API_BASE/vscode/scan/$RUNTIME_SESSION_ID" >/dev/null 2>&1 || true

wait "$CODE_PID"
