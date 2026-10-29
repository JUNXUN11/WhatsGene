# Changelog

Append after each task: what Muse did, and tick `docs/ROADMAP.md` when a task completes a phase (see `AGENTS.md`).

## 29 Oct 2026 — Docs + boilerplate

- Added `AGENTS.md`, `docs/blast-rules.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`.
- Scaffolded `backend/` (FastAPI + SQLite) and `frontend/` (Nuxt) boilerplate. No BLAST logic yet.

## 29 Oct 2026 — PRD v0.3 and doc alignment (Muse)

- Rewrote `docs/PRD.md` to v0.3 (positioning, delegate-and-verify, tiers, Muse Spark Open via Modal); recorded 8 open questions instead of resolving them.
- Aligned `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `AGENTS.md` and `docs/blast-rules.md` to v0.3, one file at a time with owner approval.

## 29 Oct 2026 — Boilerplate rework to v0.3 (Muse)

- Backend: intent + rules engine + verification modules; bounded agent loop with step log, budget, next-candidate/adjusted-retry recovery; BLAST backend interface with fixture backend; WhatsApp chat handling (job start, one-running-per-chat + cancel, grounded follow-ups, forget-history); Muse Spark Open via Modal config.
- Eval harness: offline fixtures for globin/insulin/RBP4 cases — 15 tests pass. Live NCBI and live WhatsApp/Modal sends are not wired yet and fail loudly.
- Frontend: removed the submission form (WhatsApp-start landing), results page shows the agent step log, footer shows "Built with Muse Spark Open". Build and full-stack smoke pass.

## 29 Oct 2026 — Roadmap sync + per-task changelog rule (Muse)

- Added the per-task rule to `AGENTS.md`: after each task, append what Muse did here and tick `docs/ROADMAP.md` if a phase is done.
- Synced `docs/ROADMAP.md` to actual progress: 30 Oct ticked on its offline done-when; progress notes added to 29 and 31 Oct (live WhatsApp/NCBI still remaining).
