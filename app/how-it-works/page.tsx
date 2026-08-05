import ImagePlaceholder from "../../components/ImagePlaceholder";

export default function HowItWorksPage() {
  return (
    <section className="section">
      <div className="container page-grid">
        <article className="panel">
          <h1>How It Works</h1>
          <p>
            Browser requests checkout with SKU only. The server resolves
            authoritative product pricing, records orders, and waits for a
            verified webhook before creating entitlements.
          </p>
        </article>
        <ImagePlaceholder
          title="How-it-works sequence diagram"
          fileHint="public/images/how-it-works.webp"
          recommendedSize="1600x1000"
        />
      </div>
    </section>
  );
}
