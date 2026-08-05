import LicenseStatus from "../../../components/LicenseStatus";
import ImagePlaceholder from "../../../components/ImagePlaceholder";

export default function AccountLicensesPage() {
  return (
    <section className="section">
      <div className="container page-grid">
        <article className="panel">
          <h1>License Requests</h1>
          <p>Owner-issued offline license fulfillment status appears here.</p>
          <LicenseStatus status="PENDING" />
        </article>
        <ImagePlaceholder
          title="License request visual"
          fileHint="public/images/account-licenses.webp"
          recommendedSize="1400x900"
        />
      </div>
    </section>
  );
}
