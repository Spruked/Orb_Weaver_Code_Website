import ImagePlaceholder from "../../components/ImagePlaceholder";

export default function SecurityPage() {
  return (
    <section className="section">
      <div className="container page-grid">
        <article className="panel">
          <h1>Security</h1>
          <p>
            Offline operation supported. Checkout fulfillment is gated by verified
            server-to-server webhook events before entitlement creation.
          </p>
        </article>
        <ImagePlaceholder
          title="Security architecture visual"
          fileHint="public/images/security.webp"
          recommendedSize="1600x1000"
        />
      </div>
    </section>
  );
}
