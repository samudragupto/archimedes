/** @type {import('next').NextConfig} */
const nextConfig = {
  // Lint runs separately (`pnpm typecheck` + editor); builds stay fast and
  // deterministic — type errors still fail the build, which is the gate that
  // matters for the type-safe end-to-end bar.
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;
