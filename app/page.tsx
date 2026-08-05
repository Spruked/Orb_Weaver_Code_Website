import Link from "next/link";
import VerificationPanel from "../components/VerificationPanel";
import ImagePlaceholder from "../components/ImagePlaceholder";

export default function HomePage() {
  return (
    <section className="section">
      <div className="container page-grid">
        <div className="panel">
          <p>Local-first code provenance</p>
          <h1>Your code has a history. Now it can prove it.</h1>
          <p>
            Orb Weaver Code-Cipher gives source files a verifiable identity,
            records human and AI contributions, detects unauthorized changes,
            and preserves a private chain of custody.
          </p>
          <p>
            No vendor telemetry. No mandatory cloud account. No phone-home
            license validation.
          </p>
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
            <Link href="/pricing" className="button button-primary">View Pricing</Link>
            <Link href="/how-it-works" className="button">See How It Works</Link>
          </div>
        </div>

        <div>
          <VerificationPanel />
          <div style={{ height: "1rem" }} />
          <ImagePlaceholder
            title="Homepage hero visual placeholder"
            fileHint="public/images/home-hero.webp"
            recommendedSize="1920x1080"
          />
        </div>
      </div>
    </section>
  );
}
