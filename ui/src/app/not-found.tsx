import Link from "next/link";

import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4 text-center">
      <p className="text-sm font-medium text-brand-700">404</p>
      <h1 className="mt-2 text-2xl font-semibold">Page not found</h1>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">
        The page you were looking for does not exist, or you may not have access to it.
      </p>
      <Button className="mt-6" asChild>
        <Link href="/">Back to home</Link>
      </Button>
    </div>
  );
}
