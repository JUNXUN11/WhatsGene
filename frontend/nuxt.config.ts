// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2024-11-01',
  devtools: { enabled: false },
  // SPA mode: every page loads its data in the browser, so one static
  // build runs both in dev and served from the backend (One Box).
  ssr: false,
  css: ['~/assets/css/main.css'],
  runtimeConfig: {
    public: {
      // Backend API base. The default is same origin (/api): the One Box
      // backend serves the site and the API on one address. Split setups
      // (dev without the proxy, hosted frontend) override with
      // NUXT_PUBLIC_API_BASE.
      apiBase: process.env.NUXT_PUBLIC_API_BASE || '/api',
      // Site face, baked in at build time. 'app' (default) is the local
      // tool: / redirects straight to /new. 'landing' is the hosted
      // download-only page: / renders the landing with no login button
      // and no backend calls. The hosted build sets
      // NUXT_PUBLIC_SITE_MODE=landing.
      siteMode: process.env.NUXT_PUBLIC_SITE_MODE || 'app',
    },
  },
  vite: {
    server: {
      // Two-terminal dev keeps working with no .env: the dev server
      // forwards same-origin /api calls to the backend on :8000.
      proxy: { '/api': 'http://localhost:8000' },
    },
  },
  app: {
    head: {
      title: 'WhatsGene — Find a gene, without watching BLAST',
      link: [
        { rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' },
      ],
      meta: [
        { name: 'description', content: 'WhatsGene picks the BLAST program, runs NCBI BLAST in the background, confirms the top hit, and WhatsApps you the result.' },
      ],
    },
  },
})
