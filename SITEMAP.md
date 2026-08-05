# Orb Weaver Code-Cipher Website Sitemap

This sitemap belongs to the standalone website repository:
`Spruked/Orb_Weaver_Code_Cipher_Website`

## Public Pages

- /
- /how-it-works
- /code-vin
- /provenance
- /integrations
- /security
- /pricing
- /documentation
- /download

## Post-checkout UX Pages (non-indexed/private)

- /checkout/success
- /checkout/cancelled

## Customer Account Pages (non-indexed/private)

- /account
- /account/orders
- /account/licenses
- /account/downloads

## API Routes (non-indexed/private)

- /api/checkout
- /api/payments/webhook
- /api/orders/[orderId]
- /api/downloads/[artifactId]
- /api/license-requests

## Notes

- The machine-readable sitemap is generated from `app/sitemap.ts`.
- Set `NEXT_PUBLIC_SITE_URL` in production so canonical URLs are correct.
- Keep API endpoints and private account states out of search indexing.
