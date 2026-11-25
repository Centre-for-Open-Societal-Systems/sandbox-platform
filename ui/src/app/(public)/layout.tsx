import { SiteFooter } from "@/components/layout/site-footer";
import { SiteHeader } from "@/components/layout/site-header";

/** Pages own their width so full-bleed banners can sit above their content column. */
export default function PublicLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader />
      <main className="w-full flex-1">{children}</main>
      <SiteFooter />
    </div>
  );
}
