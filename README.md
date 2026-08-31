# Orb Weaver Code Cipher

Commercial storefront, protected release-distribution system, and local development/session evidence control plane.

This repository now carries the integrated **Session Monitor + Code Cipher** product surface. The two evidence domains remain logically separate so they can cross-check one another:

- **Session Monitor** records what happened while work was being done.
- **Code Cipher** records what source/artifact was protected, hashed, verified, and released.
- **Correlation** compares the two records and reports mismatches instead of silently reconciling them.

Repository:

- `Spruked/Orb_Weaver_Code_Website`

Private implementation/release components may still live outside this repository where appropriate. Production signing secrets and private commercial source must never be published here.

## What This Repository Contains

### Commercial website

- Next.js TypeScript website
- Signup and account APIs
- Admin APIs for users, orders, and metrics
- Checkout order creation (SKU-only browser payload)
- Verified payment webhook handler
- Entitlement and license-request records
- Protected download grant issuance (short-lived token grants)

### Session Monitor control plane

- local FastAPI monitor service on `127.0.0.1:18441`
- SQLite session index
- append-only JSONL evidence ledger
- Code Weaver Vault mirror in `code_weaver_vault/runtime`
- Git/workspace snapshots
- Codex Stats.log quota ingestion
- Codex rollout JSONL ingestion
- VS Code log/reload/IPC evidence
- session-bounded ingestion and duplicate suppression
- token/reload/quota correlation timeline
- Electron always-on-top quota widget
- Electron full local dashboard
- Next.js `/session-monitor` dashboard adapter

### Code Cipher correlation surface

- release-manifest view
- artifact SHA-256 display
- repository / Git HEAD comparison
- runtime-evidence vs release-evidence correlation
- explicit match / mismatch / unknown states

## Evidence Rule

The product does not manufacture telemetry.

Values are classified by provenance and kept separate:

- `observed` — read directly from a source/runtime
- `inferred` — derived from observed evidence
- `manual` — user-entered annotation

Unknown data remains unknown.

The Session Monitor must not derive provider quota from wall-clock time. Token consumption, quota/rate limits, and monetary cost are separate measurements.

## Local Monitor API

Run manually:

```bash
cd session_monitor
python3 server.py
```

Health check:

```bash
curl http://127.0.0.1:18441/health
```

Core routes:

```text
GET  /health
POST /sessions
POST /sessions/{id}/end
GET  /today
GET  /codex/quota
POST /codex/quota/observe/{session_id}
GET  /codex/rollout?session_id=<id>
POST /codex/rollout/ingest/{session_id}
POST /vscode/scan/{session_id}
GET  /git/{session_id}
GET  /timeline?session_id=<id>&limit=200
GET  /evidence/sources
```

Dashboard `GET` operations are read-only. Evidence enters the ledger only through explicit observation/ingestion actions.

## Electron Widget / Local Dashboard

```bash
cd widget
npm install
npm start
```

The Electron app:

- checks the monitor API at startup
- starts `session_monitor/server.py` if needed
- displays Codex primary and secondary quota separately
- opens a local full dashboard without requiring Next.js
- automatically collects active-session evidence every 15 seconds
- exposes manual evidence-collection controls for testing

See [`widget/README.md`](./widget/README.md).

## Session Monitor Parser Verification

On the real WSL machine:

```bash
cd session_monitor
python3 verify_parsers.py
```

The verifier is read-only. It confirms real source discovery/parsing without adding evidence to a session ledger.

## Environment

Copy `.env.example` to `.env.local` and set values:

- `DATABASE_URL`
- `SESSION_SECRET`
- `PAYMENT_WEBHOOK_SECRET`
- `NEXT_PUBLIC_SITE_URL`

## Database Setup

```bash
npm install
npm run db:generate
npm run db:push
```

## Run Website Locally

```bash
npm run dev
```

## Production Deployment

**Domain:** `codeweaver.certsig.com`

### Quick Setup

```bash
./setup.sh
```

This will:

- build the application
- install and enable the systemd service for auto-start/restart
- configure nginx reverse proxy
- set up SSL with Let's Encrypt when available

For manual steps see [`DEPLOYMENT.md`](./DEPLOYMENT.md).

### Deploy Updates

```bash
./deploy.sh
```

### Service Management

```bash
sudo systemctl status orb-weaver-code.service
sudo systemctl status code-weaver-session-monitor.service
sudo journalctl -u orb-weaver-code.service -f
sudo journalctl -u code-weaver-session-monitor.service -f
sudo systemctl restart orb-weaver-code.service
```

Fresh VS Code session window:

```bash
scripts/code-weaver-vscode-session.sh
```

Optional user-service install:

```bash
scripts/install-code-weaver-user-services.sh
systemctl --user status code-weaver-widget.service
systemctl --user status code-weaver-vscode-session.service
```

## Website API Routes

- Auth: `/api/auth/signup`, `/api/auth/login`, `/api/auth/logout`, `/api/auth/me`
- Checkout: `/api/checkout`
- Webhook: `/api/payments/webhook`
- Account: `/api/account/orders`, `/api/account/licenses`, `/api/account/downloads`
- Admin: `/api/admin/users`, `/api/admin/orders`, `/api/admin/metrics`

## What This Repository Must Not Contain

- production private signing keys
- public static installer binaries in `/public`
- API keys, passwords, auth tokens, or `.env` secrets
- duplicated raw prompt/response/source payloads merely for telemetry logging

## Image Placeholders

Website pages contain explicit image placeholder blocks with file hints and recommended dimensions so final visual assets can be dropped in later.

© 2026 Bryan Spruk. All rights reserved.

Orb Weaver Code Cipher is proprietary software. Unauthorized copying, redistribution, or modification is prohibited.
