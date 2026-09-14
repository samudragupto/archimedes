"use client";

import { useState } from "react";
import { Check, CircleAlert, Loader2, ShieldCheck, Sparkles } from "lucide-react";
import { Badge, ModelBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, api } from "@/lib/api";
import type { ComplianceIssue, ProjectAggregate } from "@/lib/types";
import { cn } from "@/lib/utils";

const SEVERITY_TONE: Record<string, "danger" | "warning" | "outline"> = {
  blocker: "danger",
  major: "warning",
  minor: "outline",
};

const SEVERITY_WEIGHT: Record<string, number> = { blocker: 3, major: 2, minor: 1 };

/**
 * Compliance tab: the scored audit report. Every open issue that points at a
 * section carries a one-click fix — Ultra rewrites that section against the
 * specific rule, the issue is marked resolved, and the section is saved.
 */
export function CompliancePanel({
  aggregate,
  token,
  onMutate,
}: {
  aggregate: ProjectAggregate;
  token: string;
  onMutate: () => Promise<void>;
}) {
  const [fixing, setFixing] = useState<string | null>(null);
  const [fixedIds, setFixedIds] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  const issues = [...aggregate.compliance_issues].sort(
    (a, b) => Number(a.resolved) - Number(b.resolved) || (SEVERITY_WEIGHT[b.severity] ?? 0) - (SEVERITY_WEIGHT[a.severity] ?? 0),
  );
  const score = aggregate.compliance_score;
  const unresolved = issues.filter((i) => !i.resolved);
  const sectionTitle = (id: string | null) => aggregate.sections.find((s) => s.id === id)?.title;

  async function applyFix(issue: ComplianceIssue) {
    if (!issue.id) return;
    setFixing(issue.id);
    setError(null);
    try {
      await api.fixIssue(token, issue.id);
      setFixedIds((prev) => new Set(prev).add(issue.id as string));
      await onMutate();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not apply the fix");
    } finally {
      setFixing(null);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
      {/* score card */}
      <Card className="h-fit">
        <CardHeader>
          <CardTitle className="text-base">Compliance score</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col items-center gap-3">
          <ScoreRing score={score} />
          <p className="text-center text-sm text-muted-foreground">
            100 − 25 per blocker − 10 per major − 3 per minor.{" "}
            {unresolved.length === 0
              ? "Nothing outstanding."
              : `${unresolved.length} issue${unresolved.length === 1 ? "" : "s"} outstanding.`}
          </p>
          <div className="flex flex-wrap justify-center gap-1.5">
            <Badge tone="danger">{issues.filter((i) => !i.resolved && i.severity === "blocker").length} blockers</Badge>
            <Badge tone="warning">{issues.filter((i) => !i.resolved && i.severity === "major").length} majors</Badge>
            <Badge tone="outline">{issues.filter((i) => !i.resolved && i.severity === "minor").length} minors</Badge>
          </div>
        </CardContent>
      </Card>

      {/* issue list */}
      <div className="space-y-3">
        {error && <p className="rounded-md bg-red-50 p-3 text-sm text-red-800">{error}</p>}
        {issues.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center gap-2 py-12 text-center">
              <ShieldCheck className="h-10 w-10 text-emerald-600" aria-hidden />
              <p className="font-medium">No audit results yet</p>
              <p className="max-w-md text-sm text-muted-foreground">
                Run the agent — the audit step checks every draft section against every extracted requirement
                and files its findings here.
              </p>
            </CardContent>
          </Card>
        ) : (
          issues.map((issue) => (
            <Card key={issue.id} className={cn(issue.resolved && "opacity-70")}>
              <CardHeader className="pb-2">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="flex items-start gap-2">
                    <CircleAlert
                      className={cn("mt-0.5 h-4 w-4 shrink-0", issue.resolved ? "text-emerald-600" : issue.severity === "blocker" ? "text-red-600" : issue.severity === "major" ? "text-amber-600" : "text-slate-500")}
                      aria-hidden
                    />
                    <div>
                      <CardTitle className="text-sm leading-snug">{issue.description}</CardTitle>
                      <CardDescription className="mt-1 flex flex-wrap items-center gap-2">
                        <Badge tone={SEVERITY_TONE[issue.severity]}>{issue.severity}</Badge>
                        {issue.section_id && <span>in “{sectionTitle(issue.section_id) ?? "section"}”</span>}
                        {issue.resolved && <Badge tone="success">resolved</Badge>}
                      </CardDescription>
                    </div>
                  </div>
                  {issue.suggested_fix && !issue.resolved && issue.section_id && (
                    <Button size="sm" onClick={() => applyFix(issue)} disabled={fixing !== null}>
                      {fixing === issue.id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Sparkles className="h-4 w-4" />
                      )}
                      Apply fix
                    </Button>
                  )}
                  {fixedIds.has(issue.id as string) && (
                    <span className="flex items-center gap-1 text-xs text-emerald-700">
                      <Check className="h-3.5 w-3.5" aria-hidden /> fixed
                    </span>
                  )}
                </div>
              </CardHeader>
              {issue.suggested_fix && (
                <CardContent>
                  <p className="rounded-md bg-secondary/60 p-3 text-sm">
                    <span className="font-medium">Suggested fix: </span>
                    {issue.suggested_fix}
                    {!issue.resolved && issue.section_id && (
                      <span className="mt-1 block text-xs text-muted-foreground">
                        Applying rewrites the section with{" "}
                        <ModelBadge modelUsed="ultra" /> and marks this issue resolved.
                      </span>
                    )}
                  </p>
                </CardContent>
              )}
            </Card>
          ))
        )}
      </div>
    </div>
  );
}

function ScoreRing({ score }: { score: number | null }) {
  if (score === null) {
    return (
      <div className="flex h-32 w-32 items-center justify-center rounded-full border-4 border-dashed border-border text-sm text-muted-foreground">
        not audited
      </div>
    );
  }
  const R = 52;
  const C = 2 * Math.PI * R;
  const color = score >= 90 ? "stroke-emerald-500" : score >= 75 ? "stroke-amber-500" : "stroke-red-500";
  return (
    <div className="relative h-32 w-32">
      <svg viewBox="0 0 128 128" className="h-32 w-32 -rotate-90">
        <circle cx="64" cy="64" r={R} className="fill-none stroke-secondary" strokeWidth="10" />
        <circle
          cx="64"
          cy="64"
          r={R}
          className={cn("fill-none transition-[stroke-dashoffset] duration-1000", color)}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={C}
          strokeDashoffset={C * (1 - score / 100)}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-bold">{score}</span>
        <span className="text-xs text-muted-foreground">/ 100</span>
      </div>
    </div>
  );
}
