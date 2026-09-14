import Link from "next/link";
import { redirect } from "next/navigation";
import { ArrowRight, Bot, FileSearch, ListChecks, ScanSearch, ShieldCheck, Sparkles } from "lucide-react";
import { Logo } from "@/components/layout/logo";
import { Badge, ModelBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { supabaseServer } from "@/lib/supabase/server";

const STEPS = [
  {
    icon: ScanSearch,
    title: "1 · Upload the solicitation",
    body: "Drop the RFP PDF (or paste a URL). Archimedes extracts every deadline, budget cap, page limit and eligibility rule — each one proven against a verbatim source quote.",
  },
  {
    icon: FileSearch,
    title: "2 · Live research",
    body: "Nemotron Super plans the research; Tavily runs it against the live web. Findings keep real URLs — citations are never fabricated.",
  },
  {
    icon: Bot,
    title: "3 · Draft & audit",
    body: "Nemotron Ultra drafts each section, Super audits it against the extracted rules, and one click applies scored fixes. Export to MD, DOCX or PDF.",
  },
];

export default async function LandingPage() {
  // Signed-in users land straight in the workspace. Unconfigured local envs
  // (no Supabase keys yet) must still see the landing page, not a 500.
  let signedIn = false;
  try {
    const supabase = supabaseServer();
    const {
      data: { user },
    } = await supabase.auth.getUser();
    signedIn = user !== null;
  } catch {
    signedIn = false;
  }
  if (signedIn) redirect("/dashboard");

  return (
    <main>
      <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-5">
        <div className="flex items-center gap-2 font-semibold">
          <Logo />
          <span className="text-lg tracking-tight">Archimedes</span>
        </div>
        <Link href="/login">
          <Button variant="outline" size="sm">
            Sign in
          </Button>
        </Link>
      </header>

      {/* hero */}
      <section className="mx-auto max-w-6xl px-4 pb-16 pt-14 text-center sm:pt-20">
        <Badge tone="outline" className="mb-5">
          <Sparkles className="mr-1 h-3.5 w-3.5" /> Autonomous grant-writing agent
        </Badge>
        <h1 className="mx-auto max-w-3xl text-4xl font-bold tracking-tight sm:text-6xl">
          Win grants, <span className="text-primary">not paperwork.</span>
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-lg text-muted-foreground">
          Grant writers cost $100–200 an hour; most small non-profits can&apos;t. Archimedes reads the
          solicitation, researches live sources, drafts the full proposal on NVIDIA Nemotron, and audits
          it against every requirement — end to end, in minutes.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Link href="/login">
            <Button size="lg">
              Start writing free <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
          <Link href="/login?demo=1">
            <Button size="lg" variant="outline">
              See the demo project
            </Button>
          </Link>
        </div>

        {/* tier language: every AI action in the product names its model */}
        <div className="mt-10 flex flex-wrap items-center justify-center gap-2 text-xs text-muted-foreground">
          <span className="mr-1">Every step names its model:</span>
          <ModelBadge modelUsed="nvidia/Llama-3_1-Nemotron-Nano-8B-v1" />
          <ModelBadge modelUsed="nvidia/Llama-3_3-Nemotron-Super-49B-v1" />
          <ModelBadge modelUsed="nvidia/Llama-3_1-Nemotron-Ultra-253B-v1" />
          <ModelBadge modelUsed="tavily" />
        </div>
      </section>

      {/* how it works */}
      <section className="mx-auto max-w-6xl px-4 pb-20">
        <div className="grid gap-4 md:grid-cols-3">
          {STEPS.map((step) => (
            <Card key={step.title}>
              <CardHeader>
                <step.icon className="mb-2 h-7 w-7 text-primary" aria-hidden />
                <CardTitle className="text-base">{step.title}</CardTitle>
                <CardDescription>{step.body}</CardDescription>
              </CardHeader>
            </Card>
          ))}
        </div>

        <div className="mt-10 grid gap-4 sm:grid-cols-3">
          {[
            { icon: ListChecks, label: "Scored compliance report", body: "0–100 score; blockers, majors, minors — each with a one-click fix drafted by Ultra." },
            { icon: ShieldCheck, label: "Your data stays yours", body: "Private storage bucket, row-level security, owner-only access on every table." },
            { icon: Bot, label: "Watch it work", body: "A live console streams every model call, tool call and token cost while the agent runs." },
          ].map((item) => (
            <div key={item.label} className="flex gap-3 rounded-lg border bg-card/60 p-4">
              <item.icon className="mt-0.5 h-5 w-5 shrink-0 text-primary" aria-hidden />
              <div>
                <p className="text-sm font-semibold">{item.label}</p>
                <p className="mt-1 text-sm text-muted-foreground">{item.body}</p>
              </div>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
