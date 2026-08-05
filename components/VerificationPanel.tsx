const rows = [
  ["Status", "VERIFIED"],
  ["Record Type", "DEMONSTRATION RECORD"],
  ["Code VIN", "CV1-OWR1-7K4P9M2X-Q8R6T1HC"],
  ["Repository", "Spruked/Orb_Weaver_Code_Cipher"],
  ["Signature", "VALID"],
  ["Chain", "INTACT"],
];

export default function VerificationPanel() {
  return (
    <div className="verification-panel">
      <div className="verification-header">
        <span className="status-indicator" />
        <span>CODE-CIPHER VERIFICATION (DEMO)</span>
      </div>
      <div className="verification-body">
        {rows.map(([label, value]) => (
          <div className="verification-row" key={label}>
            <span>{label}</span>
            <code>{value}</code>
          </div>
        ))}
      </div>
    </div>
  );
}
