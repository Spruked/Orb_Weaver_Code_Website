import ImagePlaceholder from "../../../components/ImagePlaceholder";

export default function AccountOrdersPage() {
  return (
    <section className="section">
      <div className="container page-grid">
        <article className="panel">
          <h1>Orders</h1>
          <p>Order status history: pending, paid, fulfillment, refunded, disputed.</p>
        </article>
        <ImagePlaceholder
          title="Orders history visual"
          fileHint="public/images/account-orders.webp"
          recommendedSize="1400x900"
        />
      </div>
    </section>
  );
}
