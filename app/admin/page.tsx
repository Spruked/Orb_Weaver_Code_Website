import ImagePlaceholder from "../../components/ImagePlaceholder";

export default function AdminPage() {
  return (
    <section className="section">
      <div className="container page-grid">
        <article className="panel">
          <h1>Admin Console</h1>
          <p>
            Backend admin routes provide user management, order oversight, and
            accounting metrics through protected API endpoints.
          </p>
          <ul>
            <li>/api/admin/users</li>
            <li>/api/admin/orders</li>
            <li>/api/admin/metrics</li>
          </ul>
        </article>
        <ImagePlaceholder
          title="Admin dashboard visual"
          fileHint="public/images/admin.webp"
          recommendedSize="1600x1000"
        />
      </div>
    </section>
  );
}
