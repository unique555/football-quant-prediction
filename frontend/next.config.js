/** @type {import('next').NextConfig} */
const apiBase =
  process.env.INTERNAL_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  (process.env.NODE_ENV === "production"
    ? "http://backend:8000"
    : "http://localhost:8000");

const nextConfig = {
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "**" },
    ],
  },
  async rewrites() {
    return [
      {
        source: "/v1/:path*",
        destination: `${apiBase}/v1/:path*`,
      },
      {
        source: "/health",
        destination: `${apiBase}/health`,
      },
      {
        source: "/api/v1/:path*",
        destination: `${apiBase}/v1/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
