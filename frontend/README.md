# WhatsGene — Frontend (Nuxt)

Nuxt (Vue 3, TypeScript). Landing page, workflow submission, parallel job manager with live status, rich results, and Ask box. WhatsApp is deferred; see decision 004.
Talks to the FastAPI backend — see `../docs/ARCHITECTURE.md`.

## Run

```bash
cd frontend
npm install
npm run dev
```

- App: http://localhost:3000
- Backend expected at http://localhost:8000 (override with `NUXT_PUBLIC_API_BASE`)

Start the backend first (see `../backend/README.md`).
