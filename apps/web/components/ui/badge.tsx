import { cn } from "@/lib/utils";
import { TIER_LABEL, tierOf, type Tier } from "@/lib/types";

type Tone = "default" | "success" | "warning" | "danger" | "outline" | "nano" | "super" | "ultra" | "tavily";

const TONES: Record<Tone, string> = {
  default: "bg-primary text-primary-foreground",
  success: "bg-emerald-100 text-emerald-900 border border-emerald-300",
  warning: "bg-amber-100 text-amber-900 border border-amber-300",
  danger: "bg-red-100 text-red-900 border border-red-300",
  outline: "border border-input text-foreground",
  nano: "bg-emerald-50 text-emerald-800 border border-emerald-300",
  super: "bg-blue-50 text-blue-800 border border-blue-300",
  ultra: "bg-purple-50 text-purple-800 border border-purple-300",
  tavily: "bg-orange-50 text-orange-800 border border-orange-300",
};

/** Colored pill. Tier tones map to the model-tier color language. */
export function Badge({
  tone = "default",
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        TONES[tone],
        className,
      )}
      {...props}
    />
  );
}

/** Badge for a Nemotron model id (or Tavily) — e.g. provenance on every section/event. */
export function ModelBadge({ modelUsed, className }: { modelUsed: string | null | undefined; className?: string }) {
  const tier = tierOf(modelUsed);
  if (!tier) return null;
  const tone: Tone = tier === "tavily" ? "tavily" : (tier as Tier);
  return (
    <Badge tone={tone} className={className}>
      {TIER_LABEL[tier]}
    </Badge>
  );
}
