import { Suspense } from "react";
import { LoginForm } from "@/components/auth/login-form";
import { Skeleton } from "@/components/ui/progress";

/** `?next=` and `?error=` are read via useSearchParams — Next requires a Suspense boundary. */
export default function LoginPage() {
  return (
    <Suspense fallback={<main className="mx-auto max-w-md px-4 py-20"><Skeleton className="h-96 w-full" /></main>}>
      <LoginForm />
    </Suspense>
  );
}
