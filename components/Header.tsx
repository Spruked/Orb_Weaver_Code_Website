import Link from "next/link";

const nav = [
  { label: "How It Works", href: "/how-it-works" },
  { label: "Code VIN", href: "/code-vin" },
  { label: "AI Provenance", href: "/provenance" },
  { label: "Integrations", href: "/integrations" },
  { label: "Security", href: "/security" },
  { label: "Pricing", href: "/pricing" },
  { label: "Documentation", href: "/documentation" },
  { label: "Download", href: "/download" },
];

export default function Header() {
  return (
    <header className="site-header">
      <div className="container header-inner">
        <Link href="/" className="brand" aria-label="Orb Weaver Code-Cipher">
          <span className="brand-mark">OW</span>
          <span className="brand-copy">
            <strong>Orb Weaver</strong>
            <span>Code-Cipher</span>
          </span>
        </Link>

        <nav className="desktop-navigation" aria-label="Primary navigation">
          {nav.map((item) => (
            <Link className="nav-link" href={item.href} key={item.href}>
              {item.label}
            </Link>
          ))}
        </nav>

        <Link href="/checkout" className="button button-primary button-small">
          Buy License
        </Link>
      </div>
    </header>
  );
}
