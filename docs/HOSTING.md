# WhatsGene — Deployment

WhatsGene is a local tool. Pick the smallest shape that fits.

| Who uses it | Run |
|---|---|
| Only you, on your machine | `./start`: opens `http://127.0.0.1:8000`, no login while you are the only account |
| Your lab, on a trusted network | `./start --share`: prints the network address; plain HTTP; add people in Settings → Accounts |
| A team, over the internet | The Docker stack below: HTTPS, login always on, sign-up off |

## 1. Private HTTPS server (Docker)

```
Browser ──HTTPS──> Caddy ──┬── /       ──> Nuxt frontend (:3000)
                           └── /api/*  ──> FastAPI backend (:8000, prefix stripped)
Backend ──> SQLite volume (/data/whatsgene.db)
        ──> ./blastdb on the host (read-only)
        ──> NCBI, EBI MAFFT, Muse endpoint: only when a user opts in
```

You need a Linux server with 2 vCPU, 4 GB RAM and 25 GB of disk. You also need a hostname whose DNS `A` record points at the server, with ports 22, 80 and 443 open.

```bash
curl -fsSL https://get.docker.com | sh
ufw allow OpenSSH && ufw allow 80,443/tcp && ufw --force enable
git clone https://github.com/JUNXUN11/WhatsGene.git whatsgene && cd whatsgene
```

## 2. Put the BLAST database on the server

The backend reads `./blastdb/` next to `docker-compose.yml`. At a minimum, it needs `swissprot.*`, `sprot.taxidmap`, `names.dmp` and `nodes.dmp`.

**Build the database on the server.** A built BLAST database is tied to one machine architecture, so a copy from a Mac fails on Linux with `MDB_INVALID`. Copy or download the FASTA source, then build:

```bash
# Sources: uniprot_sprot.fasta + sprot.taxidmap (UniProt), names.dmp + nodes.dmp (NCBI taxdmp.zip)
mkdir -p blastdb && cp blastdb-src/names.dmp blastdb-src/nodes.dmp blastdb-src/sprot.taxidmap blastdb/
docker compose run --rm --no-deps \
  -v "$PWD/blastdb-src:/src:ro" -v "$PWD/blastdb:/out" backend \
  makeblastdb -in /src/uniprot_sprot.fasta -dbtype prot -parse_seqids \
  -taxid_map /src/sprot.taxidmap -out /out/swissprot

# Check: this must print the human beta-globin sequence
docker compose run --rm --no-deps -v "$PWD/blastdb:/blastdb:ro" backend \
  blastdbcmd -db /blastdb/swissprot -entry P68871 -outfmt "%f" | head -3
```

No database? Local workflows then fail with a clear error. Set `SEARCH_BACKEND=ncbi` to use NCBI for every search instead.

## 3. Configure and start

```bash
cp .env.production.example .env
nano .env                  # DOMAIN, AUTH_PASSWORD, NCBI_EMAIL at minimum
docker compose up -d --build
docker compose ps          # caddy, frontend, backend all "Up"
```

- `DOMAIN`: your hostname, with no `https://`. Caddy gets a certificate once DNS points at the server.
- `AUTH_USERNAME`, `AUTH_PASSWORD`: the owner account, created on first start. Use a new, long password. Changing `.env` later does not change an existing account; use Settings → Accounts.
- `NCBI_EMAIL`: a real contact email, needed for the "real NCBI" option.
- `MODEL_ASK_ENABLED`, `MUSE_*`: leave Ask off until login and a local search work. Quotas, the answer cache and the kill switch are built in.

Compose forces `AUTH_MODE=multi`, `ALLOW_SIGNUP=false` and `COOKIE_SECURE=true`. Login works only over HTTPS on your domain.

## 4. Check the deployment

```bash
curl -fsS https://<DOMAIN>/api/health
docker compose exec backend blastp -version
docker compose exec backend ls /blastdb
```

Then, in a private browser window:

1. Log in as the owner.
2. Run `P68871` with the question "Identify this protein". It reaches `done / confirmed`.
3. Run `PNLHGLFGRKTG`. The stored parameters show E 200000, word size 2, PAM30.
4. Ask a follow-up on a finished workflow. The answer quotes stored values.

## 5. Operations

```bash
docker compose logs -f backend    # worker and searches
docker compose restart backend    # after editing .env
git pull && docker compose up -d --build    # update
docker compose cp backend:/data/whatsgene.db ./backup.db    # backup
```

| Problem | Fix |
|---|---|
| No certificate | DNS does not point at the server yet, or port 80/443 is blocked. `docker compose logs caddy` shows the error. |
| Login fails | You are on plain HTTP or the wrong hostname. Secure cookies need HTTPS on `DOMAIN`. |
| API calls fail with 401 or CORS | `NUXT_PUBLIC_API_BASE` must be `https://<DOMAIN>/api`. Rebuild the frontend after you change `DOMAIN`. |
| NCBI workflow stays at running | NCBI queue load. It aborts cleanly after 30 min. Do not poll faster than 60 s. |
