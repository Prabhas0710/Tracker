import type { NextConfig } from "next";

const backend = (process.env.BACKEND_URL || "http://127.0.0.1:9843").replace(/\/$/, "");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  allowedDevOrigins: ["192.168.29.191", "127.0.0.1", "localhost"],
  async redirects() {
    return [
      {
        source: "/dashboard",
        destination: "/expenses",
        permanent: false,
      },
      {
        source: "/chat",
        destination: "/",
        permanent: false,
      },
    ];
  },
  async headers() {
    return [
      {
        source: "/sw.js",
        headers: [
          { key: "Service-Worker-Allowed", value: "/" },
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
        ],
      },
    ];
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backend}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
