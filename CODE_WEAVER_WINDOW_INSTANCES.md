# Code Weaver Window Instances

Code Weaver uses one parent runtime session with one child instance per **human-visible VS Code window**.

The important WSL topology is:

```text
Windows desktop
├── VS Code Window A (Code.exe main window)
├── VS Code Window B (Code.exe main window)
└── ...

WSL VS Code server session
└── ~/.vscode-server/data/logs/<timestamp>/
    ├── exthost1/
    ├── exthost2/
    ├── exthost3/
    └── ...
```

A top-level Windows `Code.exe` main window is direct evidence that a visible VS Code window exists. An `exthostN` directory is a Remote WSL **extension-host evidence anchor**. It is not, by itself, proof of a one-to-one visible-window identity.

That distinction matters because one user-visible VS Code window can coexist with auxiliary/stale/additional extension hosts. Code Weaver must never force `extension-host count == visible-window count` merely to make the dashboard look tidy.

## Control-plane model

```text
Code Weaver Runtime Session
├── Global / shared evidence
│   ├── 5-hour shared plan limit
│   ├── Weekly shared plan limit
│   ├── provider limit events
│   └── release evidence
├── VS Code Window A
│   ├── Windows main-window identity
│   ├── workspace / Git identity when known
│   ├── Code Weaver child-window ID
│   ├── defensibly bound exthostN anchor when known
│   ├── IPC / reload evidence from that bound anchor
│   └── rollout / token evidence only when a thread/window identity link exists
├── VS Code Window B
│   └── same child-window fields
└── Unassigned
    ├── unbound exthostN anchors
    ├── rollout/token records with no defensible window identity
    └── other evidence that must not be guessed onto a window
```

## Dashboard tabs

The full Electron dashboard renders:

- `Global`
- one tab for each currently observed/registered VS Code window
- `Unassigned`

Shared provider quota is deliberately shown above the tabs. It is one account-level allowance and must never be duplicated or added across window tabs.

`Unassigned` is a first-class evidence state. If an exthost, rollout, token record, or IPC signal cannot be defensibly linked to a window, Code Weaver leaves it unassigned instead of manufacturing a relationship.

## Window identity classes

### OBSERVED

A child window is directly observed through one of these sources:

- Code Weaver explicitly registered the window through the tracked launcher; or
- the Windows process API observed a `Code.exe` process with a non-zero top-level main-window handle and title.

The Windows observer is read-only and is called from WSL through `powershell.exe` using an argument vector, not shell interpolation.

### DERIVED

A registered/observed child window is associated with an `exthostN` anchor through a deterministic, reproducible relationship such as a unique launch-time association. The underlying window and anchor remain separately identifiable evidence records.

### INFERRED

Evidence suggests an association but does not prove the human-visible window identity. Inferred relationships stay visibly marked and may remain in `Unassigned` rather than becoming a window tab.

## Existing open windows

The normal evidence collection scan now performs two independent observations:

1. Windows desktop observation finds actual top-level VS Code windows.
2. WSL log discovery finds active-looking `exthostN` evidence anchors.

Therefore a machine with **2 visible VS Code windows and 3 live extension hosts** is represented honestly as two window tabs plus one or more unbound extension-host anchors unless a defensible binding is available.

Future windows should still be opened with:

```bash
code-weaver-code /path/to/workspace
```

The launcher gives Code Weaver an explicit child-window record before VS Code opens and provides stronger evidence for associating the resulting desktop window and extension host.

## Implementation

- `session_monitor/windows_desktop.py`
  - read-only Windows `Code.exe` top-level main-window observation;
  - stable process/window-handle identity inside the runtime session;
  - launcher-row reconciliation by workspace/title only when unique;
  - lifecycle closure only after a successful Windows observation proves an observer-created window disappeared;
  - failed/unavailable probes never close windows.
- `session_monitor/window_instances.py`
  - Remote WSL `exthostN` discovery;
  - launcher-to-exthost binding when defensible;
  - child evidence association;
  - legacy outer server-directory cleanup.
- `session_monitor/server.py`
  - `GET /runtime/session/{session_id}/instances` returns actual window tabs separately from exthost anchors;
  - `POST /runtime/session/{session_id}/desktop-windows/observe` performs explicit desktop observation;
  - `POST /vscode/scan/{session_id}` observes both the Windows desktop and WSL extension-host topology;
  - unbound extension hosts are included in `Unassigned`, not promoted to windows.
- `scripts/code-weaver-vscode-session.sh`
  - registers a tracked child before opening VS Code;
  - attempts a unique `exthostN` binding when defensible;
  - triggers an initial instance scan.
- `widget/dashboard.html`
  - global shared-quota cards;
  - session-health strip;
  - real window-instance tabs;
  - identity-strength status pills;
  - per-window evidence/tokens/IPC/timeline panels;
  - explicit Unassigned view.

## Proof boundary

The code can distinguish visible Windows VS Code windows from WSL extension hosts. It is not `PROVEN_RUNNING` on a specific machine until the current GitHub head is pulled, the monitor/widget services are restarted, and the live scan reports the actual desktop-window count correctly.

A per-window token/turn count of zero is not automatically a failure: it means Code Weaver did not yet have a defensible thread/exthost-to-window identity link for those rollout records. Such records remain in `Unassigned` until stronger evidence exists.
