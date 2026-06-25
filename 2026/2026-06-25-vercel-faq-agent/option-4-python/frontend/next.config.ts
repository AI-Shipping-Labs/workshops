import type { NextConfig } from "next";

// Where the Python backend lives during local dev (next dev proxies API calls
// there, so the browser always uses same-origin relative paths like /chat).
const BACKEND_ORIGIN = process.env.BACKEND_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // Build to static HTML/JS/CSS (out/), which the FastAPI backend then serves —
  // just like the Lambda reference serves Vite's dist. The app is fully
  // client-side (no SSR / API routes), so it exports cleanly.
  output: "export",

  // Dev-only: proxy the agent API to the Python backend. Rewrites don't apply to
  // a static export (there's no server in prod — FastAPI serves both), so this is
  // scoped to `next dev`.
  ...(process.env.NODE_ENV === "development"
    ? {
        async rewrites() {
          return [
            { source: "/chat", destination: `${BACKEND_ORIGIN}/chat` },
            { source: "/search", destination: `${BACKEND_ORIGIN}/search` },
            { source: "/health", destination: `${BACKEND_ORIGIN}/health` },
          ];
        },
      }
    : {}),
};

export default nextConfig;
