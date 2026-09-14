"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, Loader2, MessageSquare, Save } from "lucide-react";
import { ModelBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ChatPanel } from "@/components/editor/chat-panel";
import { ApiError, api } from "@/lib/api";
import type { ProjectAggregate, Section } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Draft tab: the living proposal. Sections on the left (agent-written or
 * human-edited — provenance badge on each), a markdown editor with explicit
 * save on the right, and the context-aware chat drawer beside it.
 */
export function DraftPanel({
  aggregate,
  token,
  onMutate,
}: {
  aggregate: ProjectAggregate;
  token: string;
  onMutate: () => Promise<void>;
}) {
  const sections = aggregate.sections;
  const [selectedId, setSelectedId] = useState<string | null>(sections[0]?.id ?? null);
  const [draft, setDraft] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [chatOpen, setChatOpen] = useState(false);

  const selected = useMemo(() => sections.find((s) => s.id === selectedId) ?? sections[0] ?? null, [sections, selectedId]);

  useEffect(() => {
    setDraft(selected?.content_md ?? "");
    setSavedAt(null);
    setSaveError(null);
  }, [selected?.id, selected?.content_md]);

  const dirty = selected !== null && draft !== selected.content_md;

  async function save() {
    if (!selected) return;
    setSaving(true);
    setSaveError(null);
    try {
      await api.saveSection(token, selected.id as string, draft);
      setSavedAt(Date.now());
      await onMutate();
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : "Could not save the section");
    } finally {
      setSaving(false);
    }
  }

  if (sections.length === 0) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <p className="font-medium">No draft yet</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            Run the agent from the <strong>Agent Run</strong> tab — Archimedes will outline and draft every
            section here, with live research citations included.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className={cn("grid gap-4", chatOpen ? "lg:grid-cols-[210px_1fr_320px]" : "lg:grid-cols-[210px_1fr]")}>
      {/* section rail */}
      <Card className="h-fit">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Sections</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 p-2 pt-0">
          {sections.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => setSelectedId(s.id)}
              className={cn(
                "flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors",
                s.id === selected?.id ? "bg-primary/10 text-primary" : "hover:bg-secondary",
              )}
            >
              <span className="mt-0.5 shrink-0">
                <SectionDot status={s.status} />
              </span>
              <span className="leading-snug">{s.title}</span>
            </button>
          ))}
        </CardContent>
      </Card>

      {/* editor */}
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <CardTitle className="text-base">{selected?.title}</CardTitle>
              <CardDescription className="mt-1 flex flex-wrap items-center gap-2">
                <ModelBadge modelUsed={selected?.model_used} />
                {selected && selected.token_count > 0 && <span>{selected.token_count} tokens</span>}
                {selected?.status === "needs_revision" && (
                  <span className="text-amber-700">flagged for revision — see Compliance tab</span>
                )}
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              {savedAt && !dirty && (
                <span className="flex items-center gap-1 text-xs text-emerald-700">
                  <Check className="h-3.5 w-3.5" aria-hidden /> saved
                </span>
              )}
              <Button size="sm" onClick={save} disabled={!dirty || saving}>
                {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                Save
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {saveError && <p className="mb-3 rounded-md bg-red-50 p-3 text-sm text-red-800">{saveError}</p>}
          <textarea
            aria-label={`Edit section ${selected?.title}`}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            spellCheck
            className="min-h-[26rem] w-full resize-y rounded-md border border-input bg-card p-4 font-serif text-[15px] leading-relaxed shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <p className="mt-2 text-xs text-muted-foreground">
            Markdown supported. Inline citations like [1] refer to the research findings on the Requirements
            tab; the exported document renders them as a References list.
          </p>
        </CardContent>
      </Card>

      {/* chat drawer */}
      {chatOpen && (
        <ChatPanel
          aggregate={aggregate}
          token={token}
          onClose={() => setChatOpen(false)}
        />
      )}

      {!chatOpen && (
        <div className="lg:col-span-2">
          <Button variant="outline" size="sm" onClick={() => setChatOpen(true)}>
            <MessageSquare className="h-4 w-4" /> Open writing assistant
          </Button>
        </div>
      )}
    </div>
  );
}

function SectionDot({ status }: { status: Section["status"] }) {
  const cls =
    status === "done"
      ? "bg-emerald-500"
      : status === "needs_revision"
        ? "bg-amber-500"
        : status === "drafting"
          ? "bg-blue-500 animate-pulse-soft"
          : "bg-slate-300";
  return <span aria-hidden className={cn("inline-block h-2.5 w-2.5 rounded-full", cls)} />;
}
