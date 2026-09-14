"use client";

import { useEffect, useState } from "react";
import { CalendarClock, CircleDollarSign, FileText, ExternalLink, ShieldQuestion } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { ProjectAggregate, RequirementsDigest } from "@/lib/types";
import { accessToken } from "@/lib/supabase/client";

const CATEGORY_TONE: Record<string, "default" | "success" | "warning" | "danger" | "outline"> = {
  deadline: "danger",
  budget: "warning",
  eligibility: "default",
  section: "outline",
  format: "outline",
  evaluation: "success",
  other: "outline",
};

/**
 * Requirements tab: the machine-extracted rule sheet (every rule hoverable
 * to its verbatim source quote), the headline facts, and the live-research
 * findings with their real Tavily URLs.
 */
export function RequirementsPanel({ aggregate }: { aggregate: ProjectAggregate }) {
  const [digest, setDigest] = useState<RequirementsDigest | null>(null);

  useEffect(() => {
    let cancelled = false;
    accessToken()
      .then((token) => api.requirementsDigest(token, aggregate.id))
      .then((d) => {
        if (!cancelled) setDigest(d);
      })
      .catch(() => undefined); // digest is a convenience view; the table below still renders
    return () => {
      cancelled = true;
    };
  }, [aggregate.id]);

  return (
    <div className="space-y-6">
      {/* headline facts from the digest */}
      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-1.5">
              <CalendarClock className="h-4 w-4" /> Deadline
            </CardDescription>
            <CardTitle className="text-base">{digest?.deadline ?? "—"}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-1.5">
              <CircleDollarSign className="h-4 w-4" /> Budget / award
            </CardDescription>
            <CardTitle className="text-base">{digest?.budget ?? "—"}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-1.5">
              <FileText className="h-4 w-4" /> Page limit
            </CardDescription>
            <CardTitle className="text-base">{digest?.page_limit ?? "—"}</CardTitle>
          </CardHeader>
        </Card>
      </div>

      {/* full requirement sheet */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Extracted requirements{" "}
            <span className="ml-1 text-sm font-normal text-muted-foreground">
              ({aggregate.requirements.length}
              {digest ? `, ${digest.total_requirements} after digest` : ""})
            </span>
          </CardTitle>
          <CardDescription>
            Extracted by Nemotron Nano from your solicitation — hover a row to see the exact source sentence.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {aggregate.requirements.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              No requirements yet — run the agent (Agent Run tab) to extract them from the solicitation.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="py-2 pr-3 font-medium">Category</th>
                    <th className="py-2 pr-3 font-medium">Rule</th>
                    <th className="py-2 pr-3 font-medium">Value</th>
                    <th className="py-2 pr-3 font-medium">Mandatory</th>
                    <th className="py-2 font-medium">Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {aggregate.requirements.map((req) => (
                    <tr key={req.id} title={req.source_excerpt ?? undefined} className="border-b last:border-0 align-top">
                      <td className="py-2.5 pr-3">
                        <Badge tone={CATEGORY_TONE[req.category] ?? "outline"}>{req.category}</Badge>
                      </td>
                      <td className="py-2.5 pr-3 font-medium">{req.key}</td>
                      <td className="py-2.5 pr-3 text-muted-foreground">{req.value}</td>
                      <td className="py-2.5 pr-3">{req.is_mandatory ? "Yes" : "No"}</td>
                      <td className="py-2.5">{Math.round(req.confidence * 100)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* research findings — only Tavily-returned URLs, ever */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            Research findings
            <Badge tone="tavily">Tavily</Badge>
          </CardTitle>
          <CardDescription>
            Live web research behind this proposal. Every link was returned by a real Tavily search — nothing
            is fabricated.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {aggregate.research_findings.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              No findings yet — they appear here after the agent&apos;s research step runs.
            </p>
          ) : (
            aggregate.research_findings.map((f) => (
              <div key={f.id} className="rounded-md border p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <a
                    href={f.url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
                  >
                    {f.title} <ExternalLink className="h-3 w-3" aria-hidden />
                  </a>
                  <Badge tone="outline">relevance {Math.round(f.relevance * 100)}%</Badge>
                </div>
                <p className="mt-1 text-sm text-muted-foreground">{f.snippet}</p>
                {f.used_in_sections.length > 0 && (
                  <p className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
                    <ShieldQuestion className="h-3 w-3" aria-hidden /> cited in: {f.used_in_sections.join(", ")}
                  </p>
                )}
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}
