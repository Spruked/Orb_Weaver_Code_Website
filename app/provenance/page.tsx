import ImagePlaceholder from "../../components/ImagePlaceholder";

export default function ProvenancePage() {
  return (
    <section className="section">
      <div className="container page-grid">
        <article className="panel">
          <h1>AI Provenance</h1>
          <p>
            Human and AI contribution records are tracked for accountability while
            preserving local-first operational controls.
          </p>
        </article>
        <ImagePlaceholder
          title="Provenance chain visualization"
          fileHint="public/images/provenance.webp"
          recommendedSize="1600x1000"
        />
      </div>
    </section>
  );
}
