"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Loader2, Play, RefreshCw } from "lucide-react";
import { ModelBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { ApiError, api } from "@/lib/api";
import type { JobEvent, ProjectAggregate } from "@/lib/types";
import { relativeTime } from "@/lib/utils";

const LEVEL_STYLE: Record<string, string> = {
  info: "text-sky-700",
  model: "text-purple-700",
  tool: "text-orange-700",
  warn: "text-amber-700",
  error: "text-red-700",
};

const STEP_LABEL: Record<string, string> = {
  extract_requirements: "Extracting requirements",
  plan_research: "Planning research",
  run_research: "Researching the web",
  outline: "Outlining the proposal",
  draft_sections: "Drafting sections",
  compliance_audit: "Auditing compliance",
  revise_sections: "Revising flagged sections",
  finalize: "Finalizing document",
};

/**
 * Agent Run tab: start the pipeline, watch the live console (every model and
 * tool call with its token cost) and the progress bar. Events stream via the
 * API's ?since= cursor; the workspace page also refetches on Realtime.
 */
export function AgentRunPanel({
  aggregate,
  token,
  onMutate,
  focusJobId,
}: {
  aggregate: ProjectAggregate;
  token: string;
  onMutate: () => Promise<void>;
  focusJobId?: string | null;
}) {
  const job = aggregate.jobs.find((j) => j.id === focusJobId) ?? aggregate.jobs[0] ?? null;
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const active = job ? job.status === "queued" || job.status === "running" : false;

  const loadEvents = useCallback(async () => {
    if (!job) return;
    try {
      setEvents(await api.jobEvents(token, job.id));
    } catch {
      // transient (worker writing mid-request) — next tick retries
    }
  }, [job, token]);

  useEffect(() => {
    void loadEvents();
    if (!active) return;
    const id = setInterval(() => void loadEvents(), 2500);
    return () => clearInterval(id);
  }, [loadEvents, active]);

  async function startRun() {
    setStarting(true);
    setError(null);
    try {
      await api.run(token, aggregate.id);
      await onMutate();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start the run");
    } finally {
      setStarting(false);
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle className="text-base">The agent pipeline</CardTitle>
              <CardDescription>
                Eight LangGraph steps on NVIDIA Nemotron: extract → research → outline → draft → audit →
                revise → finalize. Watch every call live below.
              </CardDescription>
            </div>
            <Button onClick={startRun} disabled={starting || active}>
              {starting ? <Loader2 className="h-4 w-4 animate-spin" /> : active ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              {job ? (active ? "Running…" : "Re-run agent") : "Run agent"}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {error && <p className="mb-3 rounded-md bg-red-50 p-3 text-sm text-red-800">{error}</p>}
          {job?.error && (
            <p className="mb-3 flex items-start gap-2 rounded-md bg-red-50 p-3 text-sm text-red-800">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> {job.error}
            </p>
          )}

          {job ? (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium">
                  {job.current_step
                    ? (STEP_LABEL[job.current_step] ?? job.current_step)
                    : job.status === "succeeded"
                      ? "Completed"
                      : job.status === "failed"
                        ? "Failed"
                        : "Queued"}
                </span>
                <span className="text-muted-foreground">
                  {job.progress}% · runtime {job.runtime === "local" ? "local worker" : "Nebius Serverless"}
                </span>
              </div>
              <Progress value={job.progress} />
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              No runs yet. Press <strong>Run agent</strong> — requirements will be extracted, researched,
              drafted and audited automatically.
            </p>
          )}
        </CardContent>
      </Card>

      {job && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Live console</CardTitle>
            <CardDescription>
              {events.length} events{active ? " · streaming" : ""} — every line names the model that made the
              call and what it cost.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="max-h-[26rem] space-y-1.5 overflow-y-auto rounded-md bg-slate-950 p-4 font-mono text-xs leading-relaxed text-slate-200">
              {events.length === 0 && <p className="text-slate-500">Waiting for the first event…</p>}
              {events.map((ev) => (
                <div key={ev.id} className="flex flex-wrap items-baseline gap-x-2">
                  <span className="text-slate-500">{ev.ts ? relativeTime(ev.ts) : ""}</span>
                  <span className={LEVEL_STYLE[ev.level] ?? "text-slate-300"}>[{ev.level}]</span>
                  {ev.step && <span className="text-slate-400">{ev.step}:</span>}
                  <span>{ev.message}</span>
                  <ModelBadge modelUsed={ev.model_used} className="font-sans" />
                  {ev.tokens_in !== null && ev.tokens_out !== null && (
                    <span className="text-slate-500">
                      ({ev.tokens_in}→{ev.tokens_out} tok
                      {ev.latency_ms ? `, ${(ev.latency_ms / 1000).toFixed(1)}s` : ""})
                    </span>
                  )}
                </div>
              ))}
              {active && <p className="animate-pulse-soft text-slate-400">▌</p>}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
