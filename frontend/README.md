# WhatsGene — Frontend (Nuxt)

Nuxt 3 (Vue 3, TypeScript), built as a static SPA. Pages: welcome, login, new search, workflows, results with Ask, library, settings. Design: [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).

The standard run is `./start` from the repo root: it builds this app once (`npm run generate`), and the backend serves it on `http://127.0.0.1:8000`.

For frontend development with hot reload:

```bash
cd frontend
npm install
npm run dev    # http://localhost:3000, proxies /api to the backend on :8000
```

Build modes (`NUXT_PUBLIC_SITE_MODE`): `app` (default) is the tool; `landing` is the download page only, with no backend calls.
