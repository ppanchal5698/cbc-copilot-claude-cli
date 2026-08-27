import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emits a self-contained server under .next/standalone so the runtime image
  // carries neither the source tree nor the full node_modules.
  output: "standalone",
};

export default nextConfig;
