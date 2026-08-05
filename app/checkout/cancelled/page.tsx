import ImagePlaceholder from "../../../components/ImagePlaceholder";

export default function CheckoutCancelledPage() {
  return (
    <section className="section">
      <div className="container page-grid">
        <article className="panel">
          <h1>Checkout cancelled</h1>
          <p>
            No charge was finalized. You can return to pricing and restart
            checkout when ready.
          </p>
        </article>
        <ImagePlaceholder
          title="Checkout cancelled visual"
          fileHint="public/images/checkout-cancelled.webp"
          recommendedSize="1400x900"
        />
      </div>
    </section>
  );
}
