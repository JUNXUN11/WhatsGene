// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2024-11-01',
  devtools: { enabled: true },
  css: ['~/assets/css/main.css'],
  runtimeConfig: {
    public: {
      // Backend FastAPI base URL. Override with NUXT_PUBLIC_API_BASE.
      apiBase: process.env.NUXT_PUBLIC_API_BASE || 'http://localhost:8000',
    },
  },
  app: {
    head: {
      title: 'WhatsGene — Find a gene, without watching BLAST',
      meta: [
        { name: 'description', content: 'WhatsGene picks the BLAST program, runs NCBI BLAST in the background, confirms the top hit, and WhatsApps you the result.' },
      ],
    },
  },
})
