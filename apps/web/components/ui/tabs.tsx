"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

/**
 * Hand-rolled accessible tabs (roving aria-selected, keyboard arrows) — same
 * API shape as the shadcn/radix tabs without pulling radix into the tree.
 */
export function Tabs({
  tabs,
  value,
  onValueChange,
  className,
}: {
  tabs: { id: string; label: string; badge?: React.ReactNode }[];
  value: string;
  onValueChange: (id: string) => void;
  className?: string;
}) {
  return (
    <div role="tablist" aria-orientation="horizontal" className={cn("flex gap-1 overflow-x-auto", className)}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          role="tab"
          type="button"
          aria-selected={value === tab.id}
          tabIndex={value === tab.id ? 0 : -1}
          onKeyDown={(e) => {
            const i = tabs.findIndex((t) => t.id === value);
            if (e.key === "ArrowRight") onValueChange(tabs[(i + 1) % tabs.length].id);
            if (e.key === "ArrowLeft") onValueChange(tabs[(i - 1 + tabs.length) % tabs.length].id);
          }}
          onClick={() => onValueChange(tab.id)}
          className={cn(
            "inline-flex items-center gap-2 whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-medium transition-colors",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            value === tab.id
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          {tab.label}
          {tab.badge}
        </button>
      ))}
    </div>
  );
}

/** Panel wrapper that only renders when active. */
export function TabValue({ active, children }: { active: boolean; children: React.ReactNode }) {
  if (!active) return null;
  return (
    <div role="tabpanel" className="mt-6">
      {children}
    </div>
  );
}
