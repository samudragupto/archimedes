"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import { Logo } from "@/components/layout/logo";
import { Button } from "@/components/ui/button";
import { supabaseBrowser } from "@/lib/supabase/client";

import { useEffect, useState } from "react";

/** App header: brand, signed-in email (self-fetched if not passed), sign out. */
export function SiteHeader({ email: initialEmail }: { email?: string }) {
  const router = useRouter();
  const [email, setEmail] = useState(initialEmail ?? "");

  useEffect(() => {
    if (initialEmail) return;
    supabaseBrowser()
      .auth.getUser()
      .then(({ data }) => setEmail(data.user?.email ?? ""))
      .catch(() => undefined);
  }, [initialEmail]);

  async function signOut() {
    await supabaseBrowser().auth.signOut();
    router.replace("/login");
  }

  return (
    <header className="border-b bg-card/70">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <Link href="/dashboard" className="flex items-center gap-2 font-semibold">
          <Logo /> <span className="tracking-tight">Archimedes</span>
        </Link>
        <div className="flex items-center gap-3">
          {email && <span className="hidden text-sm text-muted-foreground sm:block">{email}</span>}
          <Button variant="ghost" size="sm" onClick={signOut}>
            <LogOut className="h-4 w-4" /> Sign out
          </Button>
        </div>
      </div>
    </header>
  );
}
