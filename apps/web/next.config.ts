import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  devIndicators: false, // the dev-mode badge covers the sidebar in demos
  distDir: process.env.NEXT_DIST_DIR || ".next", // lets a hosted-mode preview run next to the local one
};

export default nextConfig;
