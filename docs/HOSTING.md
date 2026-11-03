# WhatsGene — Hosting guide (single VPS, local + real NCBI search)

> **Superseded as product direction (2 Nov 2026, decision 008):**
> WhatsGene is a local tool on the owner's own server, not a hosted
> service. The `README.md` tutorial is the primary install path. Keep
> this guide only for an owner who wants the tool on a private server
> with HTTPS. The public-host plans below (A to E) are kept for the
> record and are not the plan any more.

Chosen setup (owner, 2 Nov 2026): **1A** one VPS running the whole stack
with Docker Compose, **2C** local BLAST as the server default with real
NCBI search selectable per workflow. **Free plan (owner, 2 Nov 2026):
pay USD 0 — Oracle Cloud Always Free as the host (§1), Cloudflare Tunnel
from your Mac as the no-card fallback.** This guide plus the Docker files
in the repo root are the deliverable; nothing is deployed yet.

```
Browser ──HTTPS──> Caddy ──┬── /       ──> Nuxt frontend (:3000)
                           └── /api/*  ──> FastAPI backend (:8000, prefix stripped)
Backend ──> SQLite volume (/data/whatsgene.db)
        ──> ./blastdb on the host (SwissProt copy, read-only)
        ──> NCBI E-utilities + BLAST URL API (only for "real NCBI" workflows)
        ──> Muse endpoint (only when MODEL_ASK_ENABLED=true)
        ──> EBI MAFFT (only when a user runs Align on a finished job)
```

## 1. The free plan (pay USD 0)

**Plan A — Oracle Cloud Always Free (the submission host).** This is the
only free tier that fits WhatsGene without cutting features: an always-on
Arm VM that never sleeps, with a persistent disk for SQLite and the
BLAST DB.

- You get: **Ampere A1, 2 OCPU / 12 GB RAM, 200 GB disk total** (limits
  halved by Oracle in June 2026 — still 3× the RAM this stack needs).
- Use: **one VM, 2 OCPU / 12 GB, 50 GB boot disk**, Ubuntu 24.04 (Arm).
  Docker, Caddy, Let's Encrypt, NCBI and MAFFT are all free on top.
- Cost: **USD 0, forever**, if you stay on Always Free resources and
  never click "Upgrade to Pay As You Go".
- Catch 1 — card for signup: Oracle requires a real credit/debit card
  for identity checks (no prepaid/virtual cards). It places a small
  temporary hold (~USD 1) and refunds it. Always Free resources are
  never charged. If you have no card, use Plan B.
- Catch 2 — home region is permanent: Always Free compute lives only in
  the region picked at signup and it cannot be changed. Pick
  **Singapore (`ap-singapore-1`)** — closest to Malaysia and usually
  has Arm capacity. Picking a full region first cannot be undone.
- Catch 3 — capacity and idle reclaim: "Out of capacity" at VM creation
  means retry later (do not pick a different home region in panic —
  you cannot). Oracle can reclaim truly idle free VMs, so create it
  close to the demo and keep the demo job history on it.
- Arm note: every Docker image in this repo is multi-arch, and §4
  rebuilds the BLAST DB natively on the VM. Do not reuse an x86_64 DB.

**Plan A blocked (2 Nov, owner): no credit card.** Oracle signup needs
a real credit/debit card, so Plan A cannot start. Note: a Malaysian
bank **debit** card (Visa/Mastercard, overseas online use enabled) is
not a credit card and usually passes Oracle's ~USD 1 hold — worth one
try if you have one. With no card at all, use Plan B/C below and, if
eligible, Plan D.

**Plan B — Cloudflare Tunnel from your Mac (USD 0, no card, no signup).**
Your Mac already runs the full stack with a working BLAST DB — a tunnel
just gives it a public HTTPS URL.

```bash
brew install cloudflared
# Terminal 1+2: backend (:8000) and frontend (:3000) running as usual
cloudflared tunnel --url http://localhost:3000   # quick tunnel (test only)
```

Quick-tunnel URLs are random, change on every restart, and are for
testing (200 in-flight request cap). For a stable URL you need a named
tunnel plus a domain on Cloudflare's free plan, with two ingress rules
(frontend → `:3000`, `api.` host → `:8000`, and `NUXT_PUBLIC_API_BASE` /
`FRONTEND_BASE_URL` set to match). Either way the link dies when the Mac
sleeps or loses network — rehearsal and demo-day rescue only, never the
submitted URL if reviewers may open it later.

**Plan C — Split hosting (owner choice, temporary): frontend in the
cloud, backend on the Mac.** The page gets a stable cloud address.
Search still runs on the Mac. Do the steps in this order, because each
address feeds the next step:

1. Make sure the new reviewer password works on localhost (see the
   password reset step in the chat guide). Do not start any tunnel
   with the old `dev-only-change-me` password in place.
2. On the Mac, start the backend as usual (`:8000`). Start one tunnel
   for the backend only and copy its address (`API_URL`):
   `cloudflared tunnel --url http://localhost:8000`
3. Put the frontend on Vercel (free Hobby plan): import the GitHub
   repo at [vercel.com](https://vercel.com/), set **Root Directory =
   `frontend`**, and add one environment variable before deploy:
   `NUXT_PUBLIC_API_BASE=<API_URL>` (no trailing slash). Deploy and
   copy the site address (`SITE_URL`, e.g.
   `https://whatsgene-xxx.vercel.app`). Push the latest code first —
   Vercel builds from GitHub, and the cookie fix below must be in it.
4. On the Mac, edit `backend/.env` and restart the backend:
   - `FRONTEND_BASE_URL=<SITE_URL>` — the backend accepts login and job
     requests only from this exact page address (CORS).
   - `COOKIE_SAMESITE=none` — the page and the API now live on
     different domains, so the login cookie must allow cross-site use.
     The backend forces the Secure flag with this value (code in
     `app/main.py`, test in `tests/test_auth.py`). The default `lax`
     stays correct for the one-domain Docker host in §3–§5.
   - Do not test login on `http://localhost` after this change. A
     Secure cookie does not travel on plain local HTTP. Test on the
     live Vercel address instead.
5. Open `<SITE_URL>` in a private window. Log in. Send one job with
   local search. The job must reach a done state. A page load alone
   does not prove split hosting works.
6. Know the weak point: if the backend tunnel restarts, `API_URL`
   changes. You must paste the new value into Vercel and redeploy.
   The site also dies when the Mac sleeps. Treat Plan C as a bridge
   until the backend also moves to a server (Plan A).

**Plan C fix — use Tailscale Funnel for `API_URL` (stable, no domain).**
Cloudflare quick tunnels change `API_URL` on every restart, which
forces a Vercel redeploy each time. [Tailscale Funnel](https://tailscale.com/kb/1223/funnel)
on the free Personal plan (sign in with GitHub, no card, no domain to
buy) gives the Mac a stable `https://<mac>.<tailnet>.ts.net` HTTPS
address that survives reboots (`tailscale funnel --bg 8000`). Use that
as `API_URL` in Plan C step 3. The Mac must still stay awake, so this
remains a bridge — but the submitted URL no longer rots on restart.

**Plan D — Azure for Students (only true no-card cloud VM; if eligible).**
[Azure for Students](https://azure.microsoft.com/free/students) gives
USD 100 for 12 months with **no credit card** — it verifies a school
email instead (age 18+, renewable yearly while a student). This is the
only no-card offer that runs §3–§5 unchanged: create one Ubuntu VM
(2 vCPU / 4 GB, e.g. B2s — watch the credit burn and stop the VM when
idle), then follow the Docker Compose steps as written. If you have no
school email, this plan does not exist; stay on Plan C.

**Plan E — Fully-cloud free PaaS (needs code work; not for 4 Nov).**
Frontend on Vercel/Cloudflare Pages + backend on Render Free +
workflows in Neon Free Postgres is USD 0 with no card, but only after
two changes: `SEARCH_BACKEND=ncbi` (Render's 512 MB / ephemeral disk
cannot hold the 1.6 GB BLAST DB) and moving `app/db.py` off the local
SQLite file onto Neon (free, no card, 0.5 GB). Render sleeps after
15 min idle, which kills in-flight NCBI polls, so an external pinger
(e.g. UptimeRobot free) must hit `/health` every ~10 min during the
review window. Half a day of work and a weaker demo — post-submission
only. Hugging Face Spaces is **not** an option any more: new Docker
Spaces require a paid PRO plan (checked 2 Nov 2026).

**Checked and rejected (free tiers that break this stack):**

- Render / Koyeb / Fly.io free: services sleep when idle (kills the
  background worker and NCBI polling) and disks are ephemeral (wipes
  SQLite and the 1.2 GB BLAST DB on every restart). Do not use them.
- Google Cloud always-free `e2-micro` (1 GB RAM): too small to build
  Nuxt and run BLAST. Google's USD 300 / 90-day trial would work, but
  it needs a card and everything stops when the trial ends — emergency
  bridge only, never the plan.
- Hetzner CX22 (~€4–5/month) stays the paid fallback if Oracle capacity
  fails near the deadline. It is listed here only so the price is on
  record; the free plan above does not need it.

Minimum server (any host): **2 vCPU, 4 GB RAM, 25 GB disk** (OS +
images + 1.2 GB BLAST DB + SQLite). Hostname is USD 0 with a
[DuckDNS](https://www.duckdns.org/) subdomain (`yourname.duckdns.org`)
pointing at the VM's public IP. No separate database, queue, or SSL
product is needed — SQLite and the in-process worker are in the backend.

> Free-tier facts re-checked 2 Nov 2026 against Oracle/Cloudflare/
> Render/Koyeb public pages and June–Oct 2026 limit changes; free tiers
> move often, so confirm the Always Free label on the VM shape before
> clicking Create.

## 2. Before you start

- An Oracle Always Free account with one running VM (§3, step 0):
  Ampere A1 2 OCPU / 12 GB, Ubuntu 24.04 (Arm), Singapore home region.
  A paid VPS with Ubuntu 24.04 (4 GB+) works identically if you fall back.
- A hostname pointing at that IP (DNS `A` record, or DuckDNS). In this
  guide it is `whatsgene.example.com` — replace it everywhere.
- Your local BLAST DB at `/Users/junxun/blastdb` (§4), or time to rebuild
  it on the server (§4, option B).
- **Secret warning:** your local `backend/.env` contains live WhatsApp
  and Muse keys. It is gitignored and the Docker build ignores it, so
  it will not be uploaded — but if that file was ever shared, rotate both
  keys before going live. The production secrets live only in the
  server-side `.env` created in §5.

## 3. Prepare the server

**Step 0 — create the free VM (Oracle console, Plan A only):**

1. Sign up at [cloud.oracle.com](https://cloud.oracle.com/) → Free Tier.
   Home region: **Singapore**. Card hold ~USD 1, refunded; stay on the
   Free Tier account type (never "Upgrade to Pay As You Go").
2. Console → Compute → Instances → Create instance:
   - Name: `whatsgene`; Image: **Ubuntu 24.04** (Arm / aarch64 build).
   - Shape: **VM.Standard.A1.Flex** (Ampere A1) — set **2 OCPU, 12 GB**.
     The shape must say "Always Free-eligible". If Create fails with
     "Out of capacity", wait and retry in Singapore; do not re-sign-up
     in another region (§1, Catch 2).
   - Networking: create/accept the default VCN + public subnet, assign
     a public IPv4. Add your SSH public key.
   - Boot volume: **50 GB** (200 GB total is free; leave headroom).
3. Open the network in **two** places (Oracle needs both):
   - Console: your subnet's **Security List** → add ingress rules for
     TCP `22`, `80`, `443` from `0.0.0.0/0`.
   - On the VM (step below): the host firewall rules in the shell block.
     Oracle Ubuntu images also filter with iptables — if the site does
     not load after §5, re-check both layers first (§9).

Then prepare any Ubuntu host the same way:

```bash
ssh ubuntu@<SERVER_IP>   # Oracle default user is "ubuntu", not root
sudo -i                  # the remaining commands run as root
apt-get update && apt-get -y upgrade
# Docker (official convenience script) + firewall
curl -fsSL https://get.docker.com | sh
ufw allow OpenSSH && ufw allow 80,443/tcp && ufw --force enable
# Get the code (use your public repo URL after submission prep)
git clone <REPO_URL> whatsgene && cd whatsgene
```

Only ports 22, 80, 443 are public. The backend (`:8000`) and frontend
(`:3000`) are reachable only inside the Docker network via Caddy.

## 4. Put the BLAST database on the server

Local search needs `./blastdb/` next to `docker-compose.yml` containing
at least: `swissprot.*` (the BLAST DB files), `sprot.taxidmap`,
`names.dmp`, `nodes.dmp`.

> **Do not copy your Mac's built DB to the server.** Verified 2 Nov:
> the macOS-built DB mounted into the Linux backend fails with
> `mdb_env_open: MDB_INVALID: File is not an LMDB file` — the same
> class of failure as decision 002. The FASTA source travels fine;
> the built index does not. Always rebuild on the target machine.

**Copy the source, rebuild on the server (required):**

```bash
# On your Mac: copy only the build inputs (~400 MB), not the built DB:
# (Oracle user is "ubuntu"; paths are relative to its home directory.)
rsync -av /Users/junxun/blastdb/src/ ubuntu@<SERVER_IP>:whatsgene/blastdb-src/
rsync -av /Users/junxun/blastdb/names.dmp /Users/junxun/blastdb/nodes.dmp \
  ubuntu@<SERVER_IP>:whatsgene/blastdb/

# On the server, from ~/whatsgene (backend image already has BLAST+):
mkdir -p blastdb
docker compose run --rm --no-deps \
  -v "$PWD/blastdb-src:/src:ro" -v "$PWD/blastdb:/out" backend \
  makeblastdb -in /src/uniprot_sprot.fasta -dbtype prot -parse_seqids \
  -taxid_map /src/sprot.taxidmap -out /out/swissprot
cp blastdb-src/sprot.taxidmap blastdb/
# Verify before starting the stack:
docker compose run --rm --no-deps -v "$PWD/blastdb:/blastdb:ro" backend \
  blastdbcmd -db /blastdb/swissprot -entry P68871 -outfmt "%f" | head -3
```

The verify step must print the human beta-globin sequence. This exact
rebuild (BLAST+ 2.12 in the backend image, 575,748 sequences) was
smoke-tested locally on 2 Nov: a `P68871` workflow then reached
`done/confirmed` with top hit `P68873`, E=6.55889e-106 — matching the
earlier live result. Fresh-server alternative: download
`uniprot_sprot.fasta.gz` + `sprot.taxidmap` from UniProt and
`names.dmp`/`nodes.dmp` from NCBI `taxdmp.zip` on the server instead
of rsyncing, then run the same `makeblastdb` command (decision 002).
Do not use NCBI's preformatted volumes blindly — decision 002 records
why the local build exists. On an Arm VPS (Oracle free tier), rebuild
there exactly the same way; never reuse an x86_64-built DB.

No database at all? Then local workflows fail loudly — either finish
this step or set `SEARCH_BACKEND=ncbi` in the server `.env` and accept
NCBI queue times for every search (§6).

## 5. Configure and start

```bash
cd ~/whatsgene
cp .env.production.example .env
nano .env   # set DOMAIN, AUTH_PASSWORD, NCBI_EMAIL at minimum
docker compose up -d --build
docker compose ps        # caddy, frontend, backend all "Up"
docker compose logs -f backend   # watch first startup, then Ctrl-C
```

Required `.env` values:

- `DOMAIN` — your hostname, no `https://`. Caddy cannot get a
  certificate until DNS points here and ports 80/443 are open.
- `AUTH_PASSWORD` — **must be new and long.** Your local value
  `dev-only-change-me` must never go live; the seeded `reviewer` user is
  created from this value on first backend start. If the backend has
  already started once with a weak password, change it by deleting the
  user in SQLite or wiping the `whatsgene_data` volume — editing `.env`
  afterwards does not change an existing user.
- `NCBI_EMAIL` — a real contact email. Required for real NCBI search
  (§6) and NCBI etiquette. `NCBI_API_KEY` is optional.
- `MODEL_ASK_ENABLED` — leave `false` until login + a local job pass
  (§7), then set `true` with the `MUSE_*` values to spend credit.
  Quotas (`ASK_DAILY_LIMIT`, `JOBS_DAILY_LIMIT`) and the kill switch
  already exist (decision 007).
- `WHATSAPP_*` — optional. The webhook URL is
  `https://<DOMAIN>/api/webhooks/whatsapp` with the verify token from
  `.env`. Outbound delivery stays Meta-gated (`131031`) until business
  verification passes; the website does not depend on it.

URLs are derived automatically: frontend at `https://<DOMAIN>/`, API at
`https://<DOMAIN>/api`, results links `https://<DOMAIN>/jobs/<id>`.
`COOKIE_SECURE=true` is forced by compose — correct for HTTPS, and the
reason login will fail if you test over plain HTTP/IP.

## 6. How "real search rather than local DB" works (2C)

No new code is needed — per-workflow backend choice already shipped
(decision 006). On the submission form the user (or reviewer) picks:

- **Local (server default):** real BLAST+ (`blastp`/`blastn`) against
  the server's SwissProt copy. Fast (seconds), offline, sequences never
  leave the server. Limits: SwissProt only, protein/DNA subject DB only
  — no `tblastn`/`blastx` against nucleotide DBs, and accession lookup
  only finds accessions present in SwissProt.
- **Real NCBI:** the same workflow runs against NCBI's live databases
  via E-utilities + the BLAST URL API. This is the full public BLAST:
  larger databases and every program the rules engine may pick. Costs:
  NCBI etiquette is enforced in code (one in-flight RID, polls at least
  60 s apart, abort after 30 min) and NCBI queues have waited hours in
  past live probes — the job page shows queued/running honestly, and
  the pre-run backup job (§8) covers the demo.

So the practical answer to "allow real search": keep `SEARCH_BACKEND=
local` for speed, tell the reviewer the **"real NCBI" choice on the
form** is the live-NCBI path, and make sure `NCBI_EMAIL` is set on the
server. Run one NCBI workflow right after deploy (§7) to prove it, and
keep expectations honest on the results page — an NCBI job may sit at
`running` for a long time without anything being broken.

## 7. Verify the deployment (do all of these)

```bash
curl -fsS https://<DOMAIN>/api/health        # {"status":"ok",...}
curl -fsSI https://<DOMAIN>/ | head -3       # 200, valid certificate
docker compose exec backend blastp -version  # BLAST+ present
docker compose exec backend ls /blastdb      # swissprot.*, sprot.taxidmap, names.dmp, nodes.dmp
```

Then in a private browser window:

1. Open `https://<DOMAIN>/` — homepage loads with no login.
2. `/login` with `reviewer` + the new `AUTH_PASSWORD` → succeeds.
   Logged-out `/new` bounces to `/login`.
3. Submit the beta-globin demo workflow (`NP_000509`, local backend) →
   reaches `done/confirmed` with hits, step log, exact parameters.
4. Submit a short-query workflow (`PNLHGLFGRKTG`) → stored parameters
   show E=200000, word 2, PAM30.
5. Submit one workflow with **real NCBI** selected → it queues/runs
   under its RID without erroring (completion time is NCBI's queue,
   not a pass/fail for the host). Leave it running if needed.
6. Ask one follow-up on a finished job → answer quotes stored
   E-value/identity/coverage (deterministic while
   `MODEL_ASK_ENABLED=false`).
7. If WhatsApp is configured: verification GET on the webhook URL in
   the Meta dashboard passes. Outbound delivery is still Meta-gated.

## 8. Day-to-day operations

```bash
docker compose logs -f backend      # worker + searches
docker compose logs -f frontend caddy
docker compose restart backend      # after editing .env
docker compose up -d --build        # after a code update (git pull first)
docker compose down                 # stop (volumes keep SQLite + certs)
```

- **Backup before the demo:** copy the SQLite volume file out
  (`docker compose cp backend:/data/whatsgene.db ./backup.db`) and keep
  one pre-run demo job finished on the server as the backup result.
- **Disk watch:** `df -h` — the BLAST DB, Docker images and SQLite all
  share the VPS disk. Remove old images with `docker image prune`.
- **Updates:** never edit code on the server. Commit locally, push,
  `git pull`, `docker compose up -d --build`.
- **If login suddenly fails:** you are probably on HTTP or the wrong
  hostname — `COOKIE_SECURE=true` cookies only travel over HTTPS on
  the exact `FRONTEND_BASE_URL` origin.

## 9. Troubleshooting

- **Caddy has no certificate:** DNS not yet pointing here, or 80/443
  blocked. `docker compose logs caddy` shows the ACME error verbatim.
- **Local job: "BLASTDB is not a directory" / accession not found:**
  `./blastdb` is missing or incomplete on the server (§4). The error
  names the missing piece; no partial results are shown.
- **`blastp not found`:** the backend image was built from an old
  Dockerfile. Rebuild: `docker compose up -d --build backend`.
- **Frontend loads but every API call 401/CORS-fails:** the browser is
  calling the wrong API base. `NUXT_PUBLIC_API_BASE` must be
  `https://<DOMAIN>/api` at both build and runtime (compose derives it
  from `DOMAIN` — rebuild the frontend after changing `DOMAIN`).
- **NCBI job stuck at running:** expected under NCBI queue load. It
  aborts cleanly after `NCBI_MAX_WAIT_SECONDS` (30 min) and the step
  log says so. Do not raise poll frequency — 60 s is the etiquette floor
  enforced in code.
- **Out of disk during build:** Nuxt + Python images need ~2 GB free.
  `docker image prune` first; the Oracle boot volume is 50 GB by
  default in this guide, so this should not bite unless logs grew.
- **Site unreachable after deploy (Oracle):** check both firewalls —
  Security List ingress (console) and host rules (§3, step 0.3). Oracle
  images block 80/443 by default even when the cloud rule allows them.
- **VM creation says "Out of capacity" (Oracle):** retry later in
  Singapore. Never fix this by upgrading the account or shrinking
  below 2 OCPU / 12 GB — the free allowance is the plan.

## 10. Go / no-go checklist for 4 Nov submission

- [ ] `https://<DOMAIN>/api/health` returns ok over HTTPS.
- [ ] Login works in a private window; local globin job `done/confirmed`.
- [ ] One real-NCBI workflow submitted (running is acceptable, errored
      is not) and its RID visible in the job's stored parameters.
- [ ] Pre-run backup job finished and its results page opens.
- [ ] `AUTH_PASSWORD` is not the local dev value; server `.env` is not
      in git (`git status` clean of secrets).
- [ ] README live link updated to `https://<DOMAIN>/` + reviewer login
      instructions. Oracle VM still shows as Always Free (no upgrade,
      2 OCPU / 12 GB / 50 GB) — or Plan B tunnel rehearsed as rescue.
