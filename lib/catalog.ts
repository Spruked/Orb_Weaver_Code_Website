export type ProductSku = "developer" | "team" | "enterprise";

export type Product = {
  sku: string;
  name: string;
  priceCents: number | null;
  seats?: number;
  deviceLimit?: number;
  licenseType?: string;
  salesContactRequired?: boolean;
  features?: string[];
};

export const products: Record<ProductSku, Product> = {
  developer: {
    sku: "OWCC-DEV-PERPETUAL",
    name: "Developer License",
    priceCents: 14900,
    seats: 1,
    deviceLimit: 3,
    licenseType: "perpetual",
    features: [
      "Single-user perpetual access",
      "Up to 3 personal workstations",
      "Offline operation supported",
      "Perpetual licensing",
    ],
  },
  team: {
    sku: "OWCC-TEAM-5-PERPETUAL",
    name: "Team Node License",
    priceCents: 49900,
    seats: 5,
    licenseType: "perpetual",
    features: [
      "Up to 5 seats",
      "Protected release downloads",
      "Team-level entitlement records",
      "Perpetual licensing",
    ],
  },
  enterprise: {
    sku: "OWCC-ENTERPRISE",
    name: "Sovereign Enterprise",
    priceCents: null,
    salesContactRequired: true,
    features: [
      "Sales-assisted onboarding",
      "Air-gapped operating model",
      "Custom compliance workflows",
    ],
  },
};

export function getProductBySku(sku: ProductSku): Product {
  return products[sku];
}

export function getProductByExternalSku(externalSku: string): [ProductSku, Product] {
  const entry = (Object.entries(products) as [ProductSku, Product][]).find(
    ([, product]) => product.sku === externalSku,
  );

  if (!entry) {
    throw new Error("Unknown product SKU.");
  }

  return entry;
}
