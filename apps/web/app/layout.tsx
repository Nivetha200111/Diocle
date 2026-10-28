import type { Metadata } from "next";
import "@fontsource-variable/dm-sans";
import { IBM_Plex_Mono, VT323 } from "next/font/google";
import "./globals.css";
import "./retro.css";

const pixel = VT323({ weight: "400", subsets: ["latin"], variable: "--font-pixel" });
const plexMono = IBM_Plex_Mono({ weight: ["400", "600"], subsets: ["latin"], variable: "--font-plex-mono" });

export const metadata: Metadata = {
  title: "Diocle — Legacy, reimagined.",
  description:
    "An interactive frontend preview of Diocle, the COBOL modernization workspace. All migration data is synthetic.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${pixel.variable} ${plexMono.variable}`}>{children}</body>
    </html>
  );
}
