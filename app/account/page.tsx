import ImagePlaceholder from "../../components/ImagePlaceholder";

export default function AccountPage() {
  return (
    <section className="section">
      <div className="container page-grid">
        <article className="panel">
          <h1>Account</h1>
          <p>
            Manage orders, license requests, and download activity for your
            entitlements.
          </p>
        </article>
        <ImagePlaceholder
          title="Account dashboard visual"
          fileHint="public/images/account.webp"
          recommendedSize="1600x1000"
        />
      </div>
    </section>
  );
}
