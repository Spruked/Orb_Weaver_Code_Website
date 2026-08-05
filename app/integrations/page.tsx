import ImagePlaceholder from "../../components/ImagePlaceholder";

export default function IntegrationsPage() {
  return (
    <section className="section">
      <div className="container page-grid">
        <article className="panel">
          <h1>Integrations</h1>
          <p>
            Integrate with VS Code, Neovim, and JetBrains while preserving
            customer-controlled optional networking.
          </p>
        </article>
        <ImagePlaceholder
          title="IDE integration visual"
          fileHint="public/images/integrations.webp"
          recommendedSize="1600x1000"
        />
      </div>
    </section>
  );
}
