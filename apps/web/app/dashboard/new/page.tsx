"use client";

import { useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, FileUp, Link2, Loader2, Upload } from "lucide-react";
import { SiteHeader } from "@/components/layout/site-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Textarea } from "@/components/ui/input";
import { api } from "@/lib/api";
import { accessToken } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

/**
 * 3-step wizard: solicitation → org profile → review & create.
 * Files upload only at the final step (one project id to attach them to);
 * the API parses immediately so the workspace opens with requirements.
 */

const SOLICITATION_ACCEPT = ".pdf,.txt,.md";
const ORG_ACCEPT = ".pdf,.txt,.md";

export default function NewProjectPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);

  // step 1 — solicitation
  const [solFile, setSolFile] = useState<File | null>(null);
  const [solUrl, setSolUrl] = useState("");
  const [useUrl, setUseUrl] = useState(false);

  // step 2 — org profile
  const [orgName, setOrgName] = useState("");
  const [orgText, setOrgText] = useState("");
  const [orgFile, setOrgFile] = useState<File | null>(null);

  // step 3 — review/create
  const [title, setTitle] = useState("");
  const [funder, setFunder] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const solInputRef = useRef<HTMLInputElement>(null);
  const orgInputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const step1Valid = useMemo(() => Boolean(solFile || (useUrl && solUrl.trim().length > 5)), [solFile, useUrl, solUrl]);
  const step2Valid = orgName.trim().length > 1 || orgText.trim().length > 20 || orgFile !== null;

  async function create() {
    setCreating(true);
    setError(null);
    try {
      const token = await accessToken();
      const finalTitle = title.trim() || `${orgName.trim() || "New"} proposal`;
      const project = await api.createProject(token, { title: finalTitle, funder_name: funder.trim() || undefined });

      // solicitation: file upload or URL ingest (both parse server-side now)
      if (useUrl && solUrl.trim()) {
        await api.ingestUrl(token, project.id, solUrl.trim(), "solicitation");
      } else if (solFile) {
        await api.uploadDocument(token, project.id, "solicitation", solFile);
      }

      // org profile: uploaded file, or the pasted text as a markdown blob
      if (orgFile) {
        await api.uploadDocument(token, project.id, "organization", orgFile);
      } else if (orgText.trim() || orgName.trim()) {
        const body = [`# ${orgName.trim() || "Organization profile"}`, orgText.trim()].filter(Boolean).join("\n\n");
        const blob = new File([body], "organization-profile.md", { type: "text/markdown" });
        await api.uploadDocument(token, project.id, "organization", blob);
      }

      router.push(`/dashboard/${project.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the project");
      setCreating(false);
    }
  }

  return (
    <>
      <SiteHeader />
      <main className="mx-auto max-w-3xl px-4 py-8">
        {/* step rail */}
        <ol className="mb-8 flex items-center gap-2 text-sm">
          {["Solicitation", "Organization", "Review"].map((label, i) => (
            <li key={label} className="flex flex-1 items-center gap-2">
              <span
                className={cn(
                  "flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-xs font-semibold",
                  step > i + 1 ? "border-primary bg-primary text-primary-foreground" : step === i + 1 ? "border-primary text-primary" : "text-muted-foreground",
                )}
              >
                {i + 1}
              </span>
              <span className={cn(step === i + 1 ? "font-medium" : "text-muted-foreground")}>{label}</span>
              {i < 2 && <span className="h-px flex-1 bg-border" />}
            </li>
          ))}
        </ol>

        {step === 1 && (
          <Card>
            <CardHeader>
              <CardTitle>The solicitation</CardTitle>
              <CardDescription>
                Upload the RFP (PDF/TXT/MD) or paste its URL — Archimedes extracts every requirement from it.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div
                role="button"
                tabIndex={0}
                aria-label="Upload solicitation file"
                onClick={() => solInputRef.current?.click()}
                onKeyDown={(e) => e.key === "Enter" && solInputRef.current?.click()}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragging(false);
                  const file = e.dataTransfer.files?.[0];
                  if (file) {
                    setUseUrl(false);
                    setSolFile(file);
                  }
                }}
                className={cn(
                  "flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed p-10 text-center transition-colors",
                  dragging ? "border-primary bg-primary/5" : "hover:border-primary/50 hover:bg-secondary/50",
                )}
              >
                <FileUp className="h-8 w-8 text-muted-foreground" aria-hidden />
                {solFile ? (
                  <p className="text-sm font-medium">{solFile.name}</p>
                ) : (
                  <p className="text-sm text-muted-foreground">Drop the file here, or click to browse</p>
                )}
                <input
                  ref={solInputRef}
                  type="file"
                  accept={SOLICITATION_ACCEPT}
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) {
                      setUseUrl(false);
                      setSolFile(file);
                    }
                  }}
                />
              </div>

              <div className="flex items-center gap-3 text-xs text-muted-foreground">
                <span className="h-px flex-1 bg-border" /> or <span className="h-px flex-1 bg-border" />
              </div>

              {useUrl ? (
                <div className="flex gap-2">
                  <Input
                    autoFocus
                    placeholder="https://funder.example.org/rfp.pdf"
                    value={solUrl}
                    onChange={(e) => setSolUrl(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && step1Valid && setStep(2)}
                  />
                  <Button variant="ghost" onClick={() => setUseUrl(false)}>
                    Use a file instead
                  </Button>
                </div>
              ) : (
                <Button variant="outline" className="w-full" onClick={() => setUseUrl(true)}>
                  <Link2 className="h-4 w-4" /> Ingest from a URL instead
                </Button>
              )}

              <div className="flex justify-end pt-2">
                <Button disabled={!step1Valid} onClick={() => setStep(2)}>
                  Continue <ArrowRight className="h-4 w-4" />
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {step === 2 && (
          <Card>
            <CardHeader>
              <CardTitle>Your organization</CardTitle>
              <CardDescription>
                Anything about your mission, programs and budget helps Archimedes tailor the draft. A short
                paragraph is enough — or upload an existing profile document.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="orgName">Organization name</Label>
                <Input
                  id="orgName"
                  placeholder="Riverbend Community Alliance"
                  value={orgName}
                  onChange={(e) => setOrgName(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="orgText">Mission, programs, budget — in your words</Label>
                <Textarea
                  id="orgText"
                  rows={6}
                  placeholder="501(c)(3) serving three rural counties; after-school STEM for 400 students; annual budget $850k; prior flood-warning pilot in 2024…"
                  value={orgText}
                  onChange={(e) => setOrgText(e.target.value)}
                />
              </div>
              <Button variant="outline" onClick={() => orgInputRef.current?.click()}>
                <Upload className="h-4 w-4" /> {orgFile ? orgFile.name : "Upload a profile document instead"}
              </Button>
              <input
                ref={orgInputRef}
                type="file"
                accept={ORG_ACCEPT}
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) {
                    setOrgFile(file);
                    setOrgText("");
                  }
                }}
              />
              <div className="flex justify-between pt-2">
                <Button variant="ghost" onClick={() => setStep(1)}>
                  <ArrowLeft className="h-4 w-4" /> Back
                </Button>
                <Button disabled={!step2Valid} onClick={() => setStep(3)}>
                  Continue <ArrowRight className="h-4 w-4" />
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {step === 3 && (
          <Card>
            <CardHeader>
              <CardTitle>Review & create</CardTitle>
              <CardDescription>
                Name the project — you can change everything later. Creating uploads your documents and
                extracts requirements immediately.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="title">Project title</Label>
                <Input
                  id="title"
                  placeholder="Community Flood-Sensor Network and Resident Response Program"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="funder">Funder (optional)</Label>
                <Input
                  id="funder"
                  placeholder="Community Resilience Fund"
                  value={funder}
                  onChange={(e) => setFunder(e.target.value)}
                />
              </div>

              <dl className="rounded-md bg-secondary/60 p-4 text-sm">
                <div className="flex justify-between gap-4 py-0.5">
                  <dt className="text-muted-foreground">Solicitation</dt>
                  <dd className="max-w-[60%] truncate text-right">{useUrl ? solUrl : solFile?.name}</dd>
                </div>
                <div className="flex justify-between gap-4 py-0.5">
                  <dt className="text-muted-foreground">Organization</dt>
                  <dd className="max-w-[60%] truncate text-right">
                    {orgFile?.name ?? (orgName || "pasted profile")}
                  </dd>
                </div>
              </dl>

              {error && <p className="rounded-md bg-red-50 p-3 text-sm text-red-800">{error}</p>}

              <div className="flex justify-between pt-2">
                <Button variant="ghost" onClick={() => setStep(2)} disabled={creating}>
                  <ArrowLeft className="h-4 w-4" /> Back
                </Button>
                <Button onClick={create} disabled={creating}>
                  {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
                  Create project
                </Button>
              </div>
            </CardContent>
          </Card>
        )}
      </main>
    </>
  );
}
