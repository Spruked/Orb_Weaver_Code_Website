type Props = {
  title: string;
  filename: string;
  checksum: string;
};

export default function DownloadCard({ title, filename, checksum }: Props) {
  return (
    <article className="feature-card">
      <h3>{title}</h3>
      <p>{filename}</p>
      <code>{checksum}</code>
    </article>
  );
}
