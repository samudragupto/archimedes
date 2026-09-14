import { cn } from "@/lib/utils";

/**
 * Original inline-SVG mark (MIT, drawn for this repo): an open compass "A"
 * with an orbit arc — drafting instruments + the autonomous agent loop.
 */
export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" fill="none" aria-hidden className={cn("h-8 w-8", className)}>
      <rect x="1.5" y="1.5" width="29" height="29" rx="7" className="fill-primary" />
      <path
        d="M16 7.5 9 23.5M16 7.5l7 16M11.8 18h8.4"
        stroke="currentColor"
        className="text-primary-foreground"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M6.5 24.5c2.6 2 5.9 3.2 9.5 3.2s6.9-1.2 9.5-3.2"
        stroke="currentColor"
        className="text-primary-foreground/60"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <circle cx="16" cy="7" r="2.1" className="fill-primary-foreground" />
    </svg>
  );
}
