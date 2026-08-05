import PricingCard from "../../components/PricingCard";
import ImagePlaceholder from "../../components/ImagePlaceholder";
import { products } from "../../lib/catalog";

export default function PricingPage() {
  return (
    <section className="section">
      <div className="container">
        <h1>Pricing</h1>
        <p>Perpetual licensing with local-first deployment models.</p>
        <div className="pricing-grid">
          {(Object.entries(products) as [keyof typeof products, (typeof products)[keyof typeof products]][]).map(([sku, product]) => (
            <PricingCard key={product.sku} sku={sku} product={product} />
          ))}
        </div>
        <div style={{ marginTop: "1rem" }}>
          <ImagePlaceholder
            title="Pricing support visual"
            fileHint="public/images/pricing.webp"
            recommendedSize="1600x900"
          />
        </div>
      </div>
    </section>
  );
}
