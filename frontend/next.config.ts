import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  // cacheComponents (new Next 16 mode) requires every data read to be either
  // cached or wrapped in Suspense. Our dynamic estimate pages use `use(params)`
  // and client-side fetch, which cacheComponents rejects at prerender time.
  // Keeping it off for the MVP; revisit in Phase 4 when we rework for SSR/
  // streaming + proper Suspense boundaries.
  // Note: `partialPrefetching` requires `cacheComponents`, so it goes too.
  cacheComponents: false,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
