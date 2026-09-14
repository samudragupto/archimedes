"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FileText, Loader2, Plus, Wand2 } from "lucide-react";
import { SiteHeader } from "@/components/layout/site-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/progress";
import { ApiError, api } from "@/lib/api";
import type { Project } from "@/lib/types";
import { accessToken, supabaseBrowser } from "@/lib/supabase/client";
import { formatDate } from "@/lib/utils";

const STATUS_TONE: Record<string, "default" | "success" | "warning" | "danger" | "outline"> = {
  draft: "outline",
  complete: "success",
  failed: "danger",
  extracting: "warning",
  researching: "warning",
  drafting: "warning",
  auditing: "warning",
  revising: "warning",
};

export default function DashboardPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [email, setEmail] = useState<string>("");
  const [seeding, setSeeding] = useState(false);
  const [seedError, setSeedError] = useState<string | null>(null);

  useEffect(() => {
    supabaseBrowser()
      .auth.getUser()
      .then(({ data }) => setEmail(data.user?.email ?? ""))
      .catch(() => undefined);
  }, []);

  const load = useCallback(async () => {
    try {
      const token = await accessToken();
      setProjects(await api.listProjects(token));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) router.replace("/login");
      setProjects([]);
    }
  }, [router]);

  useEffect(() => {
    void load();
  }, [load]);

  /**
   * "Try the demo project": creates the Riverbend demo proposal and starts
   * the full agent pipeline immediately. With MOCK_LLM=true on the API this
   * runs entirely offline — ideal for judges; with live keys it's a real run.
   */
  async function seedDemo() {
    setSeedError(null);
    setSeeding(true);
    try {
      const token = await accessToken();
      const project = await api.createProject(token, {
        title: "Riverbend Community Flood-Resilience Network (Demo)",
        funder_name: "Community Resilience Fund",
      });
      const { job_id } = await api.run(token, project.id);
      router.push(`/dashboard/${project.id}?job=${job_id}`);
    } catch (err) {
      setSeedError(err instanceof Error ? err.message : "Could not start the demo project");
      setSeeding(false);
    }
  }

  return (
    <>
      <SiteHeader email={email} />
      <main className="mx-auto max-w-6xl px-4 py-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Your proposals</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Each card is one solicitation Archimedes is working on with you.
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={seedDemo} disabled={seeding}>
              {seeding ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
              Try the demo project
            </Button>
            <Link href="/dashboard/new">
              <Button>
                <Plus className="h-4 w-4" /> New proposal
              </Button>
            </Link>
          </div>
        </div>

        {seedError && <p className="mt-4 rounded-md bg-red-50 p-3 text-sm text-red-800">{seedError}</p>}

        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects === null &&
            [0, 1, 2].map((i) => <Skeleton key={i} className="h-36" />)}

          {projects?.length === 0 && (
            <Card className="sm:col-span-2 lg:col-span-3">
              <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
                <FileText className="h-10 w-10 text-muted-foreground" aria-hidden />
                <p className="font-medium">No proposals yet</p>
                <p className="max-w-md text-sm text-muted-foreground">
                  Start from a solicitation PDF or URL — or press{" "}
                  <strong>Try the demo project</strong> to watch Archimedes write a complete proposal on a
                  bundled example.
                </p>
                <Link href="/dashboard/new" className="mt-2">
                  <Button>
                    <Plus className="h-4 w-4" /> New proposal
                  </Button>
                </Link>
              </CardContent>
            </Card>
          )}

          {projects?.map((project) => (
            <Link key={project.id} href={`/dashboard/${project.id}`} className="group">
              <Card className="h-full transition-shadow group-hover:shadow-md">
                <CardHeader>
                  <div className="flex items-start justify-between gap-2">
                    <CardTitle className="text-base leading-snug group-hover:text-primary">
                      {project.title}
                    </CardTitle>
                    <Badge tone={STATUS_TONE[project.status] ?? "outline"}>{project.status}</Badge>
                  </div>
                  <CardDescription>
                    {project.funder_name ? `For ${project.funder_name} · ` : ""}created {formatDate(project.created_at)}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {project.compliance_score !== null ? (
                    <p className="text-sm">
                      Compliance score{" "}
                      <strong className={project.compliance_score >= 90 ? "text-emerald-700" : project.compliance_score >= 75 ? "text-amber-700" : "text-red-700"}>
                        {project.compliance_score}/100
                      </strong>
                    </p>
                  ) : (
                    <p className="text-sm text-muted-foreground">Not audited yet</p>
                  )}
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      </main>
    </>
  );
}
