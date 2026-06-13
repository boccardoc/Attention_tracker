/** @type {import('next').NextConfig} */

// Two build modes:
//  - default (dev / node server): live API route reads SQLite on each request.
//  - STATIC=1 (GitHub Pages): fully static export; the API route is pre-rendered at
//    build time into a static JSON file (force-static in route.ts), so the deployed
//    site needs no server. BASE_PATH scopes the site under the repo name for Pages.
const isStatic = process.env.STATIC === "1";
const basePath = process.env.BASE_PATH || "";

const nextConfig = {
  experimental: {
    serverComponentsExternalPackages: ["better-sqlite3"],
  },
  ...(isStatic
    ? {
        output: "export",
        basePath: basePath || undefined,
        trailingSlash: true,
        images: { unoptimized: true },
        env: { NEXT_PUBLIC_BASE_PATH: basePath },
      }
    : {}),
};

module.exports = nextConfig;
