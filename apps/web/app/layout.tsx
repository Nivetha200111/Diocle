import type { Metadata } from "next";
import { IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import "./enterprise.css";
import "./mission/mission.css";
import "./bugs/bugs.css";

const plexMono = IBM_Plex_Mono({ weight: ["400", "600"], subsets: ["latin"], variable: "--font-plex-mono" });

export const metadata: Metadata = {
  title: "Diocle: COBOL to Java, verified",
  description:
    "AI writes the code; Diocle checks it against the original COBOL before anyone has to trust it. Built with Meta Muse Spark. Our sample programs and data are synthetic; visitor imports are labelled.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={plexMono.variable}>{children}</body>
    </html>
  );
}
