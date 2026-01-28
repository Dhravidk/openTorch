/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    const backend = process.env.CGINS_BACKEND_URL || "http://localhost:8000";
    return [
      {
        source: "/walker/:path*",
        destination: `${backend}/walker/:path*`,
      },
      {
        source: "/function/:path*",
        destination: `${backend}/function/:path*`,
      },
      {
        source: "/cl/:path*",
        destination: `${backend}/cl/:path*`,
      },
      {
        source: "/functions",
        destination: `${backend}/functions`,
      },
      {
        source: "/walkers",
        destination: `${backend}/walkers`,
      },
    ];
  },
};

export default nextConfig;
