import ImagePlaceholder from "../../../components/ImagePlaceholder";

export default function CheckoutSuccessPage() {
  return (
    <section className="section">
      <div className="container page-grid">
        <article className="panel">
          <h1>Payment received</h1>
          <p>
            This page does not grant downloads by itself. Entitlement activation
            occurs only after verified webhook processing.
          </p>
        </article>
        <ImagePlaceholder
          title="Checkout success visual"
          fileHint="public/images/checkout-success.webp"
          recommendedSize="1400x900"
        />
      </div>
    </section>
  );
}
