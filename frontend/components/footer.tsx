import ComingSoonLink from "@/components/coming-soon-link";

type FooterLink = { label: string; href: string | null };

const COLUMNS: { title: string; links: FooterLink[] }[] = [
  {
    title: "Product",
    links: [
      { label: "Overview", href: "/" },
      { label: "Optimizer", href: "/optimize" },
      { label: "Compliance", href: "/#product" },
      { label: "Changelog", href: null },
    ],
  },
  {
    title: "Company",
    links: [
      { label: "About", href: null },
      { label: "Careers", href: null },
      { label: "Contact", href: null },
    ],
  },
  {
    title: "Resources",
    links: [
      { label: "Documentation", href: null },
      { label: "API", href: null },
      { label: "Support", href: null },
    ],
  },
  {
    title: "Legal",
    links: [
      { label: "Privacy", href: null },
      { label: "Terms", href: null },
      { label: "Security", href: null },
    ],
  },
];

export default function Footer() {
  return (
    <footer className="border-t border-white/[0.06] bg-black">
      <div className="mx-auto max-w-7xl px-6 py-16 md:px-10">
        <div className="grid grid-cols-2 gap-10 sm:grid-cols-3 md:grid-cols-6">
          <div className="col-span-2 sm:col-span-3 md:col-span-2">
            <a href="/" className="flex items-center gap-2 text-[15px] font-semibold tracking-tight text-white">
              <span className="h-2 w-2 rounded-full bg-gold shadow-glow-gold" />
              grosslo
            </a>
            <p className="mt-3 max-w-xs text-sm text-neutral-500">
              AI-assisted compensation & payroll control, built on RazorpayX.
              Deterministic math, explained in plain language.
            </p>
          </div>

          {COLUMNS.map((col) => (
            <div key={col.title}>
              <h4 className="text-sm font-medium text-white">{col.title}</h4>
              <ul className="mt-4 space-y-2.5">
                {col.links.map((link) => (
                  <li key={link.label}>
                    {link.href ? (
                      <a
                        href={link.href}
                        className="text-sm text-neutral-500 transition-colors hover:text-neutral-200"
                      >
                        {link.label}
                      </a>
                    ) : (
                      <ComingSoonLink className="text-sm text-neutral-500">
                        {link.label}
                      </ComingSoonLink>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-14 flex flex-col items-start justify-between gap-4 border-t border-white/[0.06] pt-6 sm:flex-row sm:items-center">
          <p className="text-xs text-neutral-600">
            © {new Date().getFullYear()} grosslo. Built for the Razorpay AI
            Buildathon.
          </p>
          <div className="flex items-center gap-2 rounded-full border border-white/[0.08] bg-white/[0.02] px-3 py-1.5 font-mono text-xs text-neutral-500">
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400" />
            </span>
            All systems operational
          </div>
        </div>
      </div>
    </footer>
  );
}
