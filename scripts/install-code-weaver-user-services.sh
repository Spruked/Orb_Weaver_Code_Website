#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/bryan/projects/Orb_Weaver_Code_Website"
USER_SYSTEMD_DIR="$HOME/.config/systemd/user"

mkdir -p "$USER_SYSTEMD_DIR"
cp "$PROJECT_DIR/systemd/code-weaver-widget.service" "$USER_SYSTEMD_DIR/"
cp "$PROJECT_DIR/systemd/code-weaver-vscode-session.service" "$USER_SYSTEMD_DIR/"

systemctl --user daemon-reload
systemctl --user enable code-weaver-widget.service
systemctl --user enable code-weaver-vscode-session.service
systemctl --user restart code-weaver-widget.service

echo "Code Weaver user services installed."
echo "Widget status: systemctl --user status code-weaver-widget.service"
echo "VS Code session status: systemctl --user status code-weaver-vscode-session.service"
