import "@astryxdesign/core/reset.css";
import "@astryxdesign/core/astryx.css";
import "@astryxdesign/theme-neutral/theme.css";
import "./globals.css";
import type { Metadata } from "next";
import { IBM_Plex_Sans_Arabic } from "next/font/google";
import Link from "next/link";
import { LiveUpdates } from "@/components/LiveUpdates";
import { RoleSwitch } from "@/components/RoleSwitch";
import { currentRole } from "@/lib/api";
import { Providers } from "./providers";

const plex = IBM_Plex_Sans_Arabic({ subsets: ["latin", "arabic"], weight: ["400", "500", "600"], variable: "--font-plex" });

export const metadata: Metadata = {
  title: "Group finance — Example Holding",
  description: "Group finance intelligence prototype on made-up Example Holding data.",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const role = await currentRole();
  return (
    <html lang="en" dir="ltr" className={plex.variable}>
      <body>
        <Providers>
          <header className="top">
            <Link href="/" className="brand">Example Holding · Group finance</Link>
            <nav aria-label="Sections">
              <Link href="/">Group</Link>
              <Link href="/company/EH-01">Companies</Link>
              <Link href="/acquisition">Acquisition</Link>
            </nav>
            <LiveUpdates />
            <RoleSwitch role={role} />
          </header>
          {children}
        </Providers>
      </body>
    </html>
  );
}
