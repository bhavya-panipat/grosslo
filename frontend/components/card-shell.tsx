export default function CardShell({
  className = "",
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={`group relative overflow-hidden rounded-2xl border border-white/[0.08] bg-surface p-6 shadow-inner-edge transition-colors hover:border-white/[0.14] ${className}`}
    >
      {children}
    </div>
  );
}
