/** @type {import('next').NextConfig} */
const backendUrl = process.env.SERVER_API_URL ?? "http://localhost:8500";

const nextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${backendUrl}/api/v1/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
