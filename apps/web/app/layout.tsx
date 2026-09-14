import type { Metadata } from "next";
import "./globals.css";
import { Logo } from "@/components/layout/logo";

export const metadata: Metadata = {
  title: "Archimedes — autonomous grant writing",
  description:
    "Archimedes reads the solicitation, researches live sources, drafts the proposal on NVIDIA Nemotron, and audits it for compliance — built for small non-profits.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {children}
        {/* powered-by strip (text only, per the no-copyrighted-assets rule) */}
        <footer className="border-t bg-card/60 py-3">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-center gap-x-3 gap-y-1 px-4 text-center text-xs text-muted-foreground">
            <Logo className="h-4 w-4" />
            <span>
              Powered by NVIDIA Nemotron via Nebius Token Factory · Tavily live research · Supabase
            </span>
          </div>
        </footer>
      </body>
    </html>
  );
}
