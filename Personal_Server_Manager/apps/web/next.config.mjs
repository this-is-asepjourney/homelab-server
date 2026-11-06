/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    // Rewrites are resolved at build time; inside Docker the API is reachable as http://api:8000
    const apiUrl = process.env.INTERNAL_API_URL || 'http://api:8000';
    return [
      {
        source: '/api/v1/:path*',
        destination: `${apiUrl}/api/v1/:path*`,
      },
      {
        source: '/health',
        destination: `${apiUrl}/health`,
      },
      {
        source: '/install-agent.sh',
        destination: `${apiUrl}/install-agent.sh`,
      },
    ];
  },
};

export default nextConfig;
