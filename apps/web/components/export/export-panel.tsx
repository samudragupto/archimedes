"use client";

import { useEffect, useState } from "react";
import { Download, FileCode, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/progress";
import { ApiError, api } from "@/lib/api";
import type { ProjectAggregate } from "@/lib/types";
import { slugify } from "@/lib/utils";

/**
 * Export tab: live preview of the composed markdown (the exact source of the
 * DOCX/PDF renders) and one-click downloads in all three formats.
 */
export function ExportPanel({ aggregate, token }: { aggregate: ProjectAggregate; token: string }) {
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const drafted = aggregate.sections.filter((s) => s.content_md.trim().length > 0).length;

  useEffect(() => {
    let cancelled = false;
    setPreview(null);
    setError(null);
    accessTokenWhenReady();
    async function accessTokenWhenReady() {
      if (drafted === 0) return;
      try {
        const text = await api.exportText(token, aggregate.id);
        if (!cancelled) setPreview(text);
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load the preview");
      }
    }
    return () => {
      cancelled = true;
    };
  }, [aggregate.id, drafted, token]);

  async function download(format: "md" | "docx" | "pdf") {
    setBusy(format);
    setError(null);
    try {
      const blob = await api.exportBlob(token, aggregate.id, format);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${slugify(aggregate.title)}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Export failed");
    } finally {
      setBusy(null);
    }
  }

  if (drafted === 0) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <p className="font-medium">Nothing to export yet</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            Once the agent has drafted (or you have written) at least one section, the composed proposal —
            abstract, table of contents, sections and references — appears here, ready to submit.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle className="text-base">Final document</CardTitle>
              <CardDescription>
                {drafted} section{drafted === 1 ? "" : "s"} composed with abstract, contents and references.
              </CardDescription>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={() => download("md")} disabled={busy !== null}>
                <FileCode className="h-4 w-4" /> .md
              </Button>
              <Button variant="outline" size="sm" onClick={() => download("docx")} disabled={busy !== null}>
                <FileText className="h-4 w-4" /> .docx
              </Button>
              <Button size="sm" onClick={() => download("pdf")} disabled={busy !== null}>
                <Download className="h-4 w-4" /> .pdf
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {error && <p className="rounded-md bg-red-50 p-3 text-sm text-red-800">{error}</p>}
          {preview === null && !error && <Skeleton className="h-72 w-full" />}
          {preview !== null && (
            <pre className="max-h-[32rem] overflow-y-auto whitespace-pre-wrap rounded-md bg-slate-950 p-5 font-serif text-[13.5px] leading-relaxed text-slate-100">
              {preview}
            </pre>
          )}
          <p className="mt-2 text-xs text-muted-foreground">
            The preview is the exact markdown source; the .docx and .pdf renders carry the same content with
            proper headings, lists and a cover page.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
