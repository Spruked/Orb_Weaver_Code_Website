type Props = {
  status: "PENDING" | "FULFILLED" | "REJECTED";
};

export default function LicenseStatus({ status }: Props) {
  return (
    <span className={`license-status license-status-${status.toLowerCase()}`}>
      {status}
    </span>
  );
}
