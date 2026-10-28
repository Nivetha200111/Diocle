import type { NextConfig } from "next";

// Hosted on Vercel: the site and /api share one origin; Vercel forwards /api/* to the engine server
// (DIOCLE_API_ORIGIN, e.g. https://api.example.com), so the browser never talks to another host.
const apiOrigin = process.env.DIOCLE_API_ORIGIN;

const securityHeaders = [
  { key: "Strict-Transport-Security", value: "max-age=31536000" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "X-Frame-Options", value: "DENY" },
  {
    key: "Content-Security-Policy",
    value: "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'",
  },
];

const nextConfig: NextConfig = {
  devIndicators: false, // the dev-mode badge covers the sidebar
  distDir: process.env.NEXT_DIST_DIR || ".next", // lets a hosted-mode preview run next to the local one
  poweredByHeader: false,
  // Self-hosted builds are plain static files (served by Caddy); every page talks to the API from the browser.
  ...(process.env.NEXT_OUTPUT === "export"
    ? { output: "export" as const, images: { unoptimized: true } }
    : {
        async headers() {
          return apiOrigin ? [{ source: "/:path*", headers: securityHeaders }] : [];
        },
        async rewrites() {
          return apiOrigin ? [{ source: "/api/:path*", destination: `${apiOrigin}/:path*` }] : [];
        },
      }),
};

export default nextConfig;
