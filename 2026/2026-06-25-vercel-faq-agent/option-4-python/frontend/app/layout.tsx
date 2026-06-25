import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FAQ Agent — Python backend",
  description: "DataTalks.Club FAQ agent — Next.js frontend + Python (FastAPI) backend",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      {/* Browser extensions (e.g. ColorZilla) inject attributes on <body>
          before React hydrates; suppress the harmless attribute mismatch. */}
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
