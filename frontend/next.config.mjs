/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  // The browser talks to /api/*; Next forwards it to the backend container.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${process.env.BACKEND_URL ?? "http://localhost:8000"}/:path*` }];
  },
};
export default nextConfig;
