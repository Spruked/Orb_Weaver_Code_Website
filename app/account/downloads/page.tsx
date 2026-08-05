import ImagePlaceholder from "../../../components/ImagePlaceholder";

export default function AccountDownloadsPage() {
  return (
    <section className="section">
      <div className="container page-grid">
        <article className="panel">
          <h1>Downloads</h1>
          <p>
            Download grants are short-lived and tied to entitlement and artifact.
          </p>
        </article>
        <ImagePlaceholder
          title="Downloads visual"
          fileHint="public/images/account-downloads.webp"
          recommendedSize="1400x900"
        />
      </div>
    </section>
  );
}
