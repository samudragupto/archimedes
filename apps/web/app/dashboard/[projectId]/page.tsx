"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import type { RealtimeChannel } from "@supabase/supabase-js";
import { SiteHeader } from "@/components/layout/site-header";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/progress";
import { Tabs, TabValue } from "@/components/ui/tabs";
import { AgentRunPanel } from "@/components/agent/run-panel";
import { CompliancePanel } from "@/components/compliance/compliance-panel";
import { DraftPanel } from "@/components/editor/draft-panel";
import { ExportPanel } from "@/components/export/export-panel";
import { RequirementsPanel } from "@/components/requirements/requirements-panel";
import { api } from "@/lib/api";
import type { ProjectAggregate } from "@/lib/types";
import { accessToken, supabaseBrowser } from "@/lib/supabase/client";

const STATUS_TONE: Record<string, "default" | "success" | "warning" | "danger" | "outline"> = {
  draft: "outline",
  complete: "success",
  failed: "danger",
};

const ACTIVE_STATUSES = new Set(["queued", "running"]);

/**
 * The workspace. One aggregate fetch feeds all five tabs; Supabase Realtime
 * (postgres_changes on the four project tables) triggers an immediate
 * refetch, and a 4s poll of the active job's events covers any missed
 * broadcast while a run is in flight — belt and suspenders, since Realtime
 * free-tier reconnects can drop a frame exactly when a judge is watching.
 */
export default function WorkspacePage() {
  const params = useParams<{ projectId: string }>();
  const search = useSearchParams();
  const projectId = params.projectId;
  const focusJobId = search.get("job");

  const [data, setData] = useState<ProjectAggregate | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [tab, setTab] = useState("requirements");
  const [email, setEmail] = useState("");
  const tokenRef = useRef<string>("");

  const activeJob =
    data?.jobs.find((j) => j.id === focusJobId) ??
    data?.jobs.find((j) => ACTIVE_STATUSES.has(j.status)) ??
    data?.jobs[0];

  const refetch = useCallback(async () => {
    try {
      const token = tokenRef.current || (await accessToken());
      tokenRef.current = token;
      setData(await api.getProject(token, projectId));
      setLoadError(null);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Failed to load project");
    }
  }, [projectId]);

  useEffect(() => {
    supabaseBrowser()
      .auth.getUser()
      .then(({ data: user }) => setEmail(user.user?.email ?? ""))
      .catch(() => undefined);
    void refetch();
  }, [refetch]);

  // Realtime: any change on this project's rows → refetch the aggregate.
  useEffect(() => {
    let channel: RealtimeChannel | null = null;
    async function subscribe() {
      const supabase = supabaseBrowser();
      const ch = supabase.channel(`project:${projectId}`);
      for (const table of ["jobs", "sections", "compliance_issues"]) {
        ch.on("postgres_changes" as const, { event: "*", schema: "public", table, filter: `project_id=eq.${projectId}` }, () => void refetch());
      }
      ch.on("postgres_changes" as const, { event: "*", schema: "public", table: "job_events" }, () => void refetch());
      ch.subscribe();
      return ch;
    }
    // Supabase env may be unconfigured locally — realtime is an enhancement,
    // the event poll below keeps the run view live regardless.
    subscribe()
      .then((ch) => {
        channel = ch;
      })
      .catch(() => undefined);
    return () => {
      if (channel) {
        supabaseBrowser()
          .removeChannel(channel)
          .catch(() => undefined);
      }
    };
  }, [projectId, refetch]);

  // While a job is queued/running, poll the aggregate so progress advances
  // even without a Realtime connection.
  useEffect(() => {
    if (!activeJob || !ACTIVE_STATUSES.has(activeJob.status)) return;
    const id = setInterval(() => void refetch(), 4000);
    return () => clearInterval(id);
  }, [activeJob?.id, activeJob?.status, refetch]);

  if (loadError) {
    return (
      <>
        <SiteHeader email={email} />
        <main className="mx-auto max-w-6xl px-4 py-10">
          <p className="rounded-md bg-red-50 p-4 text-sm text-red-800">{loadError}</p>
        </main>
      </>
    );
  }

  if (!data) {
    return (
      <>
        <SiteHeader email={email} />
        <main className="mx-auto max-w-6xl space-y-4 px-4 py-8">
          <Skeleton className="h-9 w-2/3" />
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-64 w-full" />
        </main>
      </>
    );
  }

  const drafted = data.sections.filter((s) => s.content_md.trim().length > 0).length;
  const openIssues = data.compliance_issues.filter((i) => !i.resolved).length;

  return (
    <>
      <SiteHeader email={email} />
      <main className="mx-auto max-w-6xl px-4 py-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="max-w-2xl text-2xl font-bold tracking-tight">{data.title}</h1>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <Badge tone={STATUS_TONE[data.status] ?? "warning"}>{data.status}</Badge>
              {data.funder_name && <span>for {data.funder_name}</span>}
              {data.compliance_score !== null && (
                <span>
                  · compliance <strong className="text-foreground">{data.compliance_score}/100</strong>
                </span>
              )}
            </div>
          </div>
        </div>

        <Tabs
          className="mt-6 border-b"
          value={tab}
          onValueChange={setTab}
          tabs={[
            { id: "requirements", label: "Requirements", badge: <Badge tone="outline">{data.requirements.length}</Badge> },
            { id: "agent", label: "Agent Run", badge: activeJob ? <Badge tone={ACTIVE_STATUSES.has(activeJob.status) ? "warning" : "outline"}>{activeJob.status}</Badge> : undefined },
            { id: "draft", label: "Draft", badge: <Badge tone="outline">{drafted}/{data.sections.length || "—"}</Badge> },
            { id: "compliance", label: "Compliance", badge: openIssues > 0 ? <Badge tone="danger">{openIssues}</Badge> : <Badge tone="success">clean</Badge> },
            { id: "export", label: "Export" },
          ]}
        />

        <TabValue active={tab === "requirements"}>
          <RequirementsPanel aggregate={data} />
        </TabValue>
        <TabValue active={tab === "agent"}>
          <AgentRunPanel aggregate={data} token={tokenRef.current} onMutate={refetch} focusJobId={focusJobId} />
        </TabValue>
        <TabValue active={tab === "draft"}>
          <DraftPanel aggregate={data} token={tokenRef.current} onMutate={refetch} />
        </TabValue>
        <TabValue active={tab === "compliance"}>
          <CompliancePanel aggregate={data} token={tokenRef.current} onMutate={refetch} />
        </TabValue>
        <TabValue active={tab === "export"}>
          <ExportPanel aggregate={data} token={tokenRef.current} />
        </TabValue>
      </main>
    </>
  );
}
