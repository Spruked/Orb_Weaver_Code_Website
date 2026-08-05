import DownloadCard from "../../components/DownloadCard";
import ImagePlaceholder from "../../components/ImagePlaceholder";
import { releaseManifest } from "../../lib/release-manifest";

export default function DownloadPage() {
  return (
    <section className="section">
      <div className="container">
        <h1>Download</h1>
        <p>
          Downloads are unlocked only for paid entitlements and issued through
          short-lived grant tokens.
        </p>
        <div className="page-grid">
          <div className="panel">
            {releaseManifest.artifacts.map((artifact) => (
              <DownloadCard
                key={artifact.id}
                title={artifact.platform}
                filename={artifact.filename}
                checksum={artifact.sha256}
              />
            ))}
          </div>
          <ImagePlaceholder
            title="Download portal visual"
            fileHint="public/images/download.webp"
            recommendedSize="1600x1000"
          />
        </div>
      </div>
    </section>
  );
}
