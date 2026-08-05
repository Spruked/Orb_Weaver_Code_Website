# Orb Weaver Code-Cipher Website

Standalone commercial storefront and protected release-distribution system.

Repository target:

- Spruked/Orb_Weaver_Code_Cipher_Website

Separated product repository:

- Spruked/Orb_Weaver_Code_Cipher

## What This Repository Contains

- Next.js TypeScript website
- Signup and account APIs
- Admin APIs for users, orders, and metrics
- Checkout order creation (SKU-only browser payload)
- Verified payment webhook handler
- Entitlement and license-request records
- Protected download grant issuance (short-lived token grants)

## What This Repository Must Not Contain

- Raw commercial product source from the private implementation repository
- Public static hosting of installer binaries in `/public`
- Production private signing keys for offline license issuance

## Environment

Copy `.env.example` to `.env.local` and set values:

- DATABASE_URL
- SESSION_SECRET
- PAYMENT_WEBHOOK_SECRET
- NEXT_PUBLIC_SITE_URL

## Database Setup

```bash
npm install
npm run db:generate
npm run db:push
```

## Run Locally

```bash
npm run dev
```

## High-Level API Routes

- Auth: `/api/auth/signup`, `/api/auth/login`, `/api/auth/logout`, `/api/auth/me`
- Checkout: `/api/checkout`
- Webhook: `/api/payments/webhook`
- Account: `/api/account/orders`, `/api/account/licenses`, `/api/account/downloads`
- Admin: `/api/admin/users`, `/api/admin/orders`, `/api/admin/metrics`

## Image Placeholders

Each page has an explicit image placeholder block with a file hint and recommended dimensions so final visual assets can be dropped in later.

© 2026 Bryan [Last Name]. All rights reserved.
Orb Weaver Code‑Cipher is proprietary software. Unauthorized copying,
redistribution, or modification is prohibited.
