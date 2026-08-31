# Code Weaver Window Instances

Code Weaver uses one parent runtime session with one child instance per VS Code window.

```text
Code Weaver Runtime Session
├── Global / shared evidence
│   ├── 5-hour shared plan limit
│   ├── Weekly shared plan limit
│   ├── provider limit events
│   ├── release evidence
│   └── evidence that cannot be defensibly tied to one window
├── VS Code Instance A
│   ├── workspace / Git identity when known
│   ├── Code Weaver child-window ID
│   ├── VS Code log-session binding when known
│   ├── IPC / reload evidence from that log source
│   └── rollout / token evidence only when a thread/window identity link exists
└── VS Code Instance B
    └── same child-instance fields
```

## Dashboard tabs

The full Electron dashboard now renders:

- `Global`
- one tab for each registered or detected VS Code child instance
- `Unassigned`

Shared provider quota is deliberately shown above the tabs. It is one account-level allowance and must never be duplicated or added across window tabs.

`Unassigned` is a first-class evidence state. If a rollout/token record cannot be defensibly linked to a child window, Code Weaver keeps it global/unassigned instead of guessing.

## Window identity classes

### OBSERVED

The Code Weaver launcher explicitly registered the child window record and the stored fact came directly from that registration action.

### DERIVED

A launcher-created child was associated with exactly one new VS Code log-session directory during the launch window. The association is reproducible from timing/source evidence but is not a documented VS Code authoritative window ID.

### INFERRED

Code Weaver detected an active-looking VS Code log-session directory for a window that was already open before the tracked launcher was used. It creates a visible child tab but marks the identity limitation explicitly.

## Existing open windows

After the upgraded runtime is restarted, the normal 15-second evidence collection scan calls window-instance discovery. Recent active-looking VS Code log-session directories that are not already bound are represented as `INFERRED` child tabs.

Future windows should be opened with:

```bash
code-weaver-code /path/to/workspace
```

That gives Code Weaver an explicit child record before VS Code opens and allows the launcher to attempt a unique log-session binding.

## Implementation

- `session_monitor/window_instances.py`
  - schema extension for child-instance metadata;
  - explicit launcher decoration;
  - log-session binding;
  - active-log discovery for already-open windows;
  - child evidence association;
  - per-instance summaries;
  - unassigned evidence counts.
- `session_monitor/server.py`
  - `GET /runtime/session/{session_id}/instances`;
  - `POST /runtime/vscode-windows/{window_id}/bind-log`;
  - per-instance VS Code log scanning rather than latest-session-only scanning.
- `scripts/code-weaver-vscode-session.sh`
  - registers the child before opening VS Code;
  - snapshots existing VS Code log directories;
  - launches the new window;
  - binds a unique newly-created log-session directory as `DERIVED` when possible;
  - triggers an initial instance scan.
- `widget/dashboard.html`
  - redesigned Code Weaver control plane;
  - global shared-quota cards;
  - session-health strip;
  - window-instance tabs;
  - identity-strength status pills;
  - per-window evidence/tokens/IPC/timeline panels;
  - explicit Unassigned view.

## Proof boundary

The architecture and code are present in GitHub. It is not `PROVEN_RUNNING` on the user's machine until the change is pulled, the monitor/widget services are restarted, and the dashboard is observed showing the current VS Code windows as separate tabs.

A per-window token/turn count of zero is not automatically a failure: it means Code Weaver did not yet have a defensible thread-to-window identity link for those rollout records. Such records remain in `Unassigned` until a stronger association exists.
