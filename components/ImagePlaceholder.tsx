type Props = {
  title: string;
  fileHint: string;
  recommendedSize: string;
};

export default function ImagePlaceholder({ title, fileHint, recommendedSize }: Props) {
  return (
    <div className="image-placeholder" role="img" aria-label={title}>
      <strong>{title}</strong>
      <span>{fileHint}</span>
      <span>Recommended: {recommendedSize}</span>
    </div>
  );
}
