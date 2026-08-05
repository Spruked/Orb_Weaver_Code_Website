import ImagePlaceholder from "../../components/ImagePlaceholder";

export default function DocumentationPage() {
  return (
    <section className="section">
      <div className="container page-grid">
        <article className="panel">
          <h1>Documentation</h1>
          <p>
            API-first storefront routes, release-manifest references, and account
            fulfillment lifecycle details live here.
          </p>
        </article>
        <ImagePlaceholder
          title="Documentation visual"
          fileHint="public/images/documentation.webp"
          recommendedSize="1400x900"
        />
      </div>
    </section>
  );
}
