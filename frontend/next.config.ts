import type { NextConfig } from "next";

// No `output: "export"` in this step — combining static export with the
// rewrites-based API proxy below is a hard Next.js build error. The
// export-vs-CORS trade-off is deferred to whichever later step wires a
// production build into Flask's `/` route.
const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:8000/api/:path*",
      },
      {
        source: "/health",
        destination: "http://127.0.0.1:8000/health",
      },
    ];
  },
};

export default nextConfig;
