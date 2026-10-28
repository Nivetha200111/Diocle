import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  devIndicators: false, // the dev-mode badge covers the sidebar in demos
  distDir: process.env.NEXT_DIST_DIR || ".next", // lets a hosted-mode preview run next to the local one
  // Hosted builds are plain static files (served by Caddy); every page talks to the API from the browser.
  ...(process.env.NEXT_OUTPUT === "export" ? { output: "export" as const, images: { unoptimized: true } } : {}),
};

export default nextConfig;
