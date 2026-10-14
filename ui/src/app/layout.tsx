import type { Metadata } from "next";
import { Inter, Roboto } from "next/font/google";

import { Providers } from "@/app/providers";
import { config } from "@/lib/config";

import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

// Admin console typeface, matching the ETP registry portal template.
const roboto = Roboto({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-roboto",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: `${config.siteName} — Developer Sandbox`,
    template: `%s · ${config.siteName}`,
  },
  description:
    "Consented, standardised access to agricultural data for accredited organisations. " +
    "Open to every country in the network.",
  robots: { index: true, follow: true },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${roboto.variable}`}>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
