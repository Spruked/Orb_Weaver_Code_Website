import Link from "next/link";
import type { ProductSku, Product } from "../lib/catalog";

type Props = {
  sku: ProductSku;
  product: Product;
};

export default function PricingCard({ sku, product }: Props) {
  const priceLabel = product.priceCents
    ? `$${(product.priceCents / 100).toFixed(0)}`
    : "Custom";

  return (
    <article className={sku === "team" ? "pricing-card pricing-card-featured" : "pricing-card"}>
      {sku === "team" && <div className="pricing-badge">Most Popular</div>}
      <h2>{product.name}</h2>
      <div className="price">{priceLabel}</div>
      <div className="license-type">{product.licenseType ?? "Contact sales"}</div>
      <ul>
        {product.features?.map((feature) => (
          <li key={feature}>{feature}</li>
        ))}
      </ul>
      <Link href={sku === "enterprise" ? "/pricing" : `/checkout?sku=${product.sku}`} className="button button-primary">
        {sku === "enterprise" ? "Contact Sales" : "Purchase License"}
      </Link>
    </article>
  );
}
