import ImagePlaceholder from "../../components/ImagePlaceholder";

export default function CodeVinPage() {
  return (
    <section className="section">
      <div className="container page-grid">
        <article className="panel">
          <h1>Code VIN</h1>
          <p>
            Code VIN records are shown as clearly labeled demonstration data until
            genuine exported records are published.
          </p>
        </article>
        <ImagePlaceholder
          title="Code VIN example panel"
          fileHint="public/images/code-vin.webp"
          recommendedSize="1400x900"
        />
      </div>
    </section>
  );
}
