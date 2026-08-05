import CheckoutSummary from "../../components/CheckoutSummary";
import ImagePlaceholder from "../../components/ImagePlaceholder";

export default function CheckoutPage({
  searchParams,
}: {
  searchParams: { sku?: "developer" | "team" | "enterprise" };
}) {
  const sku = searchParams.sku ?? "developer";

  return (
    <section className="section">
      <div className="container page-grid">
        <article className="panel">
          <h1>Checkout</h1>
          <p>
            The browser sends only SKU. Server-side catalog resolution determines
            pricing and order totals.
          </p>
          <CheckoutSummary sku={sku} />
        </article>
        <ImagePlaceholder
          title="Checkout flow visual"
          fileHint="public/images/checkout.webp"
          recommendedSize="1600x1000"
        />
      </div>
    </section>
  );
}
