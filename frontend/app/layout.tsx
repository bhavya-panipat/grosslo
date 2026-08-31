import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "./globals.css";

export const metadata: Metadata = {
  title: "grosslo",
  description: "grosslo — the decision and compliance layer for RazorpayX payroll. No live dispatch, by design.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${GeistSans.variable} ${GeistMono.variable}`}
      style={
        {
          "--font-sans": GeistSans.style.fontFamily,
          "--font-display": GeistSans.style.fontFamily,
          "--font-mono": GeistMono.style.fontFamily,
        } as React.CSSProperties
      }
    >
      <body className="bg-canvas text-neutral-100 antialiased">{children}</body>
    </html>
  );
}
