"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Github, MailCheck, Wand2 } from "lucide-react";
import { Logo } from "@/components/layout/logo";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { supabaseBrowser } from "@/lib/supabase/client";

/**
 * Sign-in: Supabase magic link (passwordless email) or GitHub OAuth.
 * `?demo=1` just pre-fills the hint that a seeded demo project exists.
 */
export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(
    params.get("error") === "auth" ? "That sign-in link didn't work — try again." : null,
  );

  useEffect(() => {
    // Already signed in? Straight to the workspace.
    supabaseBrowser()
      .auth.getSession()
      .then(({ data }) => {
        if (data.session) router.replace(params.get("next") ?? "/dashboard");
      })
      .catch(() => undefined);
  }, [router, params]);

  async function sendMagicLink(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const { error: err } = await supabaseBrowser().auth.signInWithOtp({
      email,
      options: { emailRedirectTo: `${window.location.origin}/auth/callback` },
    });
    setBusy(false);
    if (err) setError(err.message);
    else setSent(true);
  }

  async function signInWithGitHub() {
    setBusy(true);
    setError(null);
    const { error: err } = await supabaseBrowser().auth.signInWithOAuth({
      provider: "github",
      options: { redirectTo: `${window.location.origin}/auth/callback` },
    });
    if (err) {
      setBusy(false);
      setError(err.message);
    }
  }

  return (
    <main className="mx-auto flex min-h-[85vh] max-w-md flex-col items-center justify-center px-4">
      <Link href="/" className="mb-6 flex items-center gap-2 text-lg font-semibold">
        <Logo /> Archimedes
      </Link>

      <Card className="w-full">
        <CardHeader>
          <CardTitle>Sign in to start writing</CardTitle>
          <CardDescription>
            No password needed — we email you a one-time link. Your projects are private to your account.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          {sent ? (
            <Alert>
              <MailCheck className="h-4 w-4" aria-hidden />
              <AlertDescription>
                Check <strong>{email}</strong> for your sign-in link. It expires in an hour.
              </AlertDescription>
            </Alert>
          ) : (
            <form onSubmit={sendMagicLink} className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="email">Work email</Label>
                <Input
                  id="email"
                  type="email"
                  required
                  placeholder="you@yournonprofit.org"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <Button type="submit" className="w-full" disabled={busy}>
                Email me a sign-in link
              </Button>
            </form>
          )}

          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span className="h-px flex-1 bg-border" /> or <span className="h-px flex-1 bg-border" />
          </div>

          <Button variant="outline" className="w-full" onClick={signInWithGitHub} disabled={busy}>
            <Github className="h-4 w-4" /> Continue with GitHub
          </Button>

          {params.get("demo") === "1" && (
            <p className="flex items-start gap-2 rounded-md bg-secondary p-3 text-xs text-secondary-foreground">
              <Wand2 className="mt-0.5 h-4 w-4 shrink-0" />
              After signing in, use the <strong>&nbsp;Try the demo project&nbsp;</strong> button on the dashboard
              to watch a full proposal being written offline (mock mode) or live.
            </p>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
