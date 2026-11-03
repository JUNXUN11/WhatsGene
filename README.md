# WhatsGene

WhatsGene is BLAST for people who do not use BLAST every day.
You submit a sequence once on the website in your browser.
WhatsGene runs the search on your own machine and records every step.
You get a plain answer with the evidence for that answer.

Built with Muse Spark Open. WhatsGene is a local tool for research and education. WhatsGene does not give medical advice.

## What local means

Local means that the program and the data run on a machine that you control.
A workflow is one search job from the submitted sequence to the final answer.
In local mode, your sequence never leaves your machine.
A local search takes seconds because the search runs beside the data.
A search in the NCBI queue waited hours in our live test runs.
Your results stay in one file on your machine, and you own that file.

## What WhatsGene does

WhatsGene picks the BLAST program for your sequence and your question.
The rules for that choice sit in code, not in the model.
WhatsGene records the program, the database, and the exact parameters for every search.
Those parameters are the E-value threshold, the word size, and the scoring matrix.
WhatsGene labels each hit as strong, borderline, or not significant with fixed rules in code.
The top hit must pass reciprocal, coverage, length, and annotation tests in code.
You can ask a follow-up question on the results page.
The answer quotes only values from your stored results, or the answer states that the stored results cannot answer the question.

A short protein query gets the short-query profile without extra work from you.
The lab case `PNLHGLFGRKTG` runs with E-value 200000, word size 2, and matrix PAM30.
The page shows those values beside the standard values E-value 10, word size 3, and matrix BLOSUM62.
A CDS subrange works too, in the form `NM_006744.4:84-689`.

## What you need

You need a Mac or a Linux machine with at least 3 GB of free disk space.
You need Python 3.12 or later, Node 20 or later, and NCBI BLAST+ 2 or later.
BLAST+ is the NCBI program set that searches a sequence against a database.
On a Mac, Homebrew installs BLAST+ with the command below.
On Ubuntu, the package manager installs BLAST+ with the command below.

```bash
# Mac
brew install blast

# Ubuntu
sudo apt-get install -y ncbi-blast+
```

## Step 1: Get the code

You run every command in this tutorial in a terminal.
The first command copies the code to your machine.
The second command moves you into the new folder.

```bash
git clone <REPO_URL> whatsgene
cd whatsgene
```

Or paste this one line in a terminal (Mac or Linux) and skip to Step 4:
it downloads the code, starts the tool, and opens your browser.

```bash
curl -fsSL <REPO_URL_RAW>/install.sh | bash
```

## Step 2: Build the search database

Skip this step on your first day: after the tool starts (Step 4), open
Settings → Local BLAST setup and press **Run setup now**. The wizard
downloads and builds this database and proves it before trusting it.
The manual commands below stay for custom setups.

The search database holds the reference sequences that BLAST searches.
You build this database once, and every later search reuses the same build.
You need three inputs in one folder, and the build command below reads all three.
UniProt gives `uniprot_sprot.fasta` and `sprot.taxidmap`, and NCBI gives `names.dmp` and `nodes.dmp` in `taxdmp.zip`.
The folder from our test build holds 575748 sequences and uses about 1.6 GB with the taxonomy files.

```bash
mkdir -p ~/blastdb
cd ~/blastdb
# Put uniprot_sprot.fasta, sprot.taxidmap, names.dmp, and nodes.dmp in this folder.
makeblastdb -in uniprot_sprot.fasta -dbtype prot -parse_seqids \
  -taxid_map sprot.taxidmap -out ~/blastdb/swissprot
blastdbcmd -db ~/blastdb/swissprot -entry P68871 -outfmt "%f" | head -3
```

The last command prints the human beta globin sequence.
If you move the tool to a new machine, build the database again on that machine.
A built database from a Mac fails on Linux, and our test log records that failure.
The `docs/HOSTING.md` file gives the server variant of this step.

## Step 3: Wire the backend to your databases

The backend is the Python program that runs the searches and stores the results.
The results file is the SQLite file that holds your workflows, hits, and step logs.
Two lines in the configuration file `backend/.env` point the backend at your data.
`BLASTDB` names the folder from Step 2, and `DATABASE_PATH` names your results file.
The example value `BLASTDB=/data/blastdb` fits only the Docker setup, so you must change that value.

```bash
cd backend
cp .env.example .env
```

In `backend/.env`, set one line to the folder from Step 2:

```bash
BLASTDB=/path/to/your/blastdb
```

That is the only line `./start` needs.
You create your account in the browser on the first run (Step 5), so `backend/.env` needs no password.
The first run also writes `AUTH_MODE=single` in `backend/.env`.
That setting keeps the browser on your own machine signed in while you are the only account.
`SEARCH_BACKEND` already means local, and `DATABASE_PATH` already means `./whatsgene.db`.
A server with no browser on the same machine cannot use the first-run page.
On such a server, set `AUTH_USERNAME` and `AUTH_PASSWORD` in `backend/.env` before the first start.
The backend then creates the owner account once, at the first start, from those values.
A later edit of the values does not change the created account.
To move your history to a new machine, copy the results file while the backend is stopped.
To use a different search database, change `BLASTDB` to the new folder and restart the backend.

## Step 4: Start the tool

One command starts the whole tool.
It prepares the Python environment, builds the website on the first run, starts the backend, and opens your browser.
The tool runs at `http://127.0.0.1:8000`, and only on your machine.
Stop it with Ctrl+C.

```bash
./start
```

Developers can still run the two parts by hand.
The backend runs in terminal 1, and the website runs in terminal 2.
You keep both terminals open while you use the tool.

```bash
# Terminal 1
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Terminal 2
cd frontend
npm install
npm run dev   # http://localhost:3000
```

## Step 5: Run your first search

Open `http://127.0.0.1:8000` in your browser (`./start` already opens it).
On the first run, the Welcome page asks for a username and a password.
That account is the owner account of your copy of the tool.
After that, the tool opens Settings on Local BLAST setup, and later runs open on New search with no login page.
Open New search and paste the accession `P68871`.
Write the question `Identify this protein` and press Run.
The workflow reaches the done status in seconds on a local database.
In our test run, the top hit was `P68873` with E-value 6.55889e-106.
The results page shows the top hit, the exact parameters, and the step log for the run.
A RefSeq accession such as `NP_000509` is not in the SwissProt copy, so local mode cannot fetch that accession.
For that case, paste the sequence text, or pick the real NCBI choice for that one workflow.

If the page does not load, make sure that `./start` still runs.
If a search reports a missing database, make sure that `BLASTDB` names the folder from Step 2.
If you see a login page and you are the only account, open the tool at `http://127.0.0.1:8000`, not at the address of your network card.
If you forget your password while you are the only account, the browser on this machine still signs you in: set a new password in Settings → Accounts.
If another person forgets a password, the owner resets it in Settings → Accounts.

## Share the tool with other people

Each person gets their own account and their own workflows.
A person can create their own account on the login page with Create an account.
The owner can also add accounts:

1. Open Settings → Accounts.
2. Under Add a person, type a username and a starting password, and press Add account.
3. Tell the person the username and the password. They can change the password in Settings → Accounts.

As soon as a second account exists, every browser asks for a login, the owner's browser too.
Make sure that you know your own password before another person gets an account.
To turn off Create an account, set `ALLOW_SIGNUP=false` in `backend/.env` and restart the tool. Then only the owner adds accounts.
The owner can reset a password or remove an account from the same page.
The workflows of a removed account move to the owner, so no result is lost.

The tool listens only on this machine by default.
For people on other computers on the same network, start the tool with this command:

```bash
./start --share
```

The command prints the address that the other computers open, for example `http://192.168.1.20:8000`.
The connection uses plain `http`, so use `--share` only on a network you trust.
For a server with HTTPS, follow `docs/HOSTING.md`.
The Docker setup always asks every browser for a login (`AUTH_MODE=multi`) and turns off Create an account (`ALLOW_SIGNUP=false`).
The decision records are `docs/decisions/016-auth-mode-single-or-multi.md` and `docs/decisions/017-owner-created-accounts.md`.

## Run the backend on another machine

You can run the backend on a lab server and the website on your laptop.
In that case, the browser must reach the backend at a public address on that server.
The `docs/HOSTING.md` file gives the Docker steps for a private server with HTTPS.
For a quick test on one network, set the two addresses below and restart both programs.
`NUXT_PUBLIC_API_BASE` goes in `frontend/.env`, and `FRONTEND_BASE_URL` goes in `backend/.env`.

```bash
# frontend/.env
NUXT_PUBLIC_API_BASE=http://<SERVER_ADDRESS>:8000

# backend/.env
FRONTEND_BASE_URL=http://<SERVER_ADDRESS>:3000
```

## Hosted download page

The public website is only a download page. Build it with
`NUXT_PUBLIC_SITE_MODE=landing`: the front page shows the install line
with no login button and makes no backend calls. The local tool always
builds with `app` (`./start` sets this), so it opens straight on New search.

## What leaves your machine

In local mode, your sequence and your results stay on your machine.
Three optional parts send data out, and each part is off or explicit.
A workflow with the real NCBI choice sends the sequence to the NCBI public BLAST service.
The Align button sends the collected sequences to the MAFFT service at EBI.
The Ask box sends stored result facts to the Muse endpoint only if `MODEL_ASK_ENABLED=true`, and the factory value is `false`.
The WhatsApp notice sends a phone number and a summary to Meta only if you fill in the WhatsApp fields.

## Limits of local mode

Local mode searches against the databases in your `BLASTDB` folder.
Step 2 builds the SwissProt copy; the Library page builds small extras on top
(PDB proteins, RefSeq viral proteins, 16S rRNA, fungi ITS, mitochondrion and viral
genomes — each built with `makeblastdb` from NCBI sources).
Local search runs `blastp` and `blastn`; `tblastn` and `blastx` need the real NCBI choice.
WhatsApp outbound delivery waits for Meta business verification.
The full science rules live in `docs/blast-rules.md`, and the product rules live in `docs/PRD.md`.

## Tests

The test suite runs offline and opens no network connection.
Every test uses recorded data, so the suite sends no sequence to NCBI and runs no BLAST+ program.
The suite covers globin, insulin, RBP4, the short-query profile, the CDS subrange, HIV-1 exclusion, and the MSA to tree step.

```bash
cd backend && .venv/bin/python -m unittest discover -s tests
cd frontend && npm run build
```

## Library: drop files, sort them, build small databases

Drop any files into `~/WhatsGene/inbox` (set `WHATSGENE_INBOX_DIR` /
`WHATSGENE_LIBRARY_DIR` in `backend/.env` to move it). Open **Library**
in the sidebar: WhatsGene reads each file and proposes what it is —
search query, database source, document, old result, or unknown. You
confirm the sorting; copies go to `~/WhatsGene/library` and originals
are never moved or deleted. A sorted query opens in New search with
one click. A sorted FASTA builds a small custom database with one
click (built with `makeblastdb` in `$BLASTDB` and registered in
`custom_databases.json` there), and the Library page can also build a
one-species database from your SwissProt copy. Custom databases then
appear under **Local database** on New search.

## MCP tools

The same library and search functions are MCP tools for any MCP host:

```bash
cd backend && .venv/bin/python -m app.mcp_server   # stdio
```

Tools: `inventory_files`, `explain_file`, `sort_files` (needs
`confirm=true`), `list_databases`, `build_custom_database`,
`build_database_from_taxon`, `run_search`, `get_workflow`,
`explain_workflow`. The model chooses tools and explains; WhatsGene
code validates, copies, builds, searches, and classifies.

## Not built yet

PSI-BLAST, PHI-BLAST, HMMER, Tajima tests, and bootstrap values are not in the tool.
The MSA and tree rules come from the course decks, and the tool invents no rule for those steps.
Accounts have two roles only: the owner, and everyone else. Password recovery by email is not in the tool.
The decision record for the local tool direction is `docs/decisions/008-local-tool-own-server.md`.

## License

WhatsGene is open source under the MIT License. See `LICENSE`.
