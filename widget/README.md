# Personal Session Monitor Widget

Small Electron tray app, frameless always-on-top quota widget, and local
full-dashboard window.

## Run

```bash
npm install
npm start
```

The widget reads the local monitor API from:

```text
http://127.0.0.1:18441
```

The tray's full-dashboard action opens `dashboard.html` from this folder, so it
does not require the Next.js dev server. The optional web-dashboard action opens:

```text
http://127.0.0.1:3000/session-monitor
```

Both values are stored in Electron's user-data settings file after first
launch:

```text
widget-settings.json
```

The widget header includes:

```text
-  hide widget
x  quit widget app
```

If hidden, click the tray icon or use "Show/Hide Widget" from the tray menu to
bring it back.

If Electron is running on Windows and the monitor server is running in WSL,
confirm Windows can reach the WSL service:

```powershell
curl http://127.0.0.1:18441/today
```

If localhost forwarding is unavailable, set `apiBase` in the settings file to
the WSL VM IP from:

```bash
wsl hostname -I
```
