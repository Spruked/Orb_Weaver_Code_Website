# Local Toolchain

This directory is part of the product, not a runtime download area.

Required layout:

```text
tools/
  mcp_server/
  chrome-devtools-mcp/
  visidata/
  TOOLCHAIN_LOCK.json
```

## Rule

All required tools are committed/vendored into this repository and included in the downloadable/deployed system. Core runtime must not fetch tools or dependencies from npm, PyPI, GitHub, hosted MCP services, CrUX, telemetry endpoints, or update services.

Do not use Git submodules for required deployment contents. The actual files must be present in repository archives and release bundles.

The first-party `mcp_server` coordinates the local tools. Chrome DevTools MCP and VisiData are used directly as local tools in unison with it; they are not wrapped in a separate Watcher adapter hierarchy.

## Chrome DevTools MCP

Source: `ChromeDevTools/chrome-devtools-mcp`

Pinned source commit is recorded in `TOOLCHAIN_LOCK.json`.

Release/runtime requirements:

- preserve upstream Apache-2.0 licensing/notices
- use the local built executable only
- disable usage statistics
- disable CrUX lookups
- disable update checks
- redact sensitive network headers where supported
- never use `npx ...@latest` at runtime

## VisiData

Source: `saulpw/visidata`

Pinned source commit is recorded in `TOOLCHAIN_LOCK.json`.

VisiData is GPL-3.0 software. Keep its complete upstream source and license with the distributed tool. Invoke it as a separate local program/tool unless a separate licensing review supports tighter integration with proprietary code.

## Release packaging

Vendoring source alone is not enough for offline runtime. Release preparation must also include the locally resolved/build runtime dependencies required by the pinned tools. Production startup must succeed with network access disabled.
