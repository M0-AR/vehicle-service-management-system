import Link from "next/link";
import { WifiOff } from "lucide-react";

import { buttonVariants } from "@/components/ui/button";

export default function OfflinePage() {
  return (
    <main id="main" className="flex min-h-screen flex-col items-center justify-center gap-4 px-4 text-center">
      <WifiOff className="h-8 w-8 text-[var(--muted-foreground)]" aria-hidden="true" />
      <h1 className="text-2xl font-semibold tracking-tight">You are offline</h1>
      <p className="max-w-md text-sm text-[var(--muted-foreground)]">
        Check your internet connection and try again. Your data is safe — changes are only saved
        when you are back online.
      </p>
      <Link href="/app" className={buttonVariants()}>
        Retry
      </Link>
    </main>
  );
}
