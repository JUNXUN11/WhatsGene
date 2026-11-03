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

## Step 2: Build the search database

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

In `backend/.env`, set these four lines with your own paths and your own password:

```bash
SEARCH_BACKEND=local
BLASTDB=/path/to/your/blastdb
DATABASE_PATH=./whatsgene.db
AUTH_PASSWORD=a-long-password-that-you-choose
```

You must set `AUTH_PASSWORD` before the first backend start.
The backend creates the login user once, at the first start, from that value.
A later edit of the value does not change the created user.
To move your history to a new machine, copy the results file while the backend is stopped.
To use a different search database, change `BLASTDB` to the new folder and restart the backend.

## Step 4: Start the tool

The backend runs in terminal 1, and the website runs in terminal 2.
You keep both terminals open while you use the tool.
The website reads the backend address from `NUXT_PUBLIC_API_BASE`, and the address in `frontend/.env.example` already fits one machine.

```bash
# Terminal 1
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Terminal 2
cd frontend
npm install
npm run dev
```

## Step 5: Run your first search

Open `http://localhost:3000` in your browser.
Log in with the user name `reviewer` and the password from Step 3.
Open New search and paste the accession `P68871`.
Write the question `Identify this protein` and press Run.
The workflow reaches the done status in seconds on a local database.
In our test run, the top hit was `P68873` with E-value 6.55889e-106.
The results page shows the top hit, the exact parameters, and the step log for the run.
A RefSeq accession such as `NP_000509` is not in the SwissProt copy, so local mode cannot fetch that accession.
For that case, paste the sequence text, or pick the real NCBI choice for that one workflow.

If the page does not load, make sure that both terminals still run.
If a search reports a missing database, make sure that `BLASTDB` names the folder from Step 2.
If login fails on the first day, make sure that the password in the browser matches `AUTH_PASSWORD` in `backend/.env`.

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

## What leaves your machine

In local mode, your sequence and your results stay on your machine.
Three optional parts send data out, and each part is off or explicit.
A workflow with the real NCBI choice sends the sequence to the NCBI public BLAST service.
The Align button sends the collected sequences to the MAFFT service at EBI.
The Ask box sends stored result facts to the Muse endpoint only if `MODEL_ASK_ENABLED=true`, and the factory value is `false`.
The WhatsApp notice sends a phone number and a summary to Meta only if you fill in the WhatsApp fields.

## Limits of local mode

Local mode searches protein sequences against the SwissProt copy from Step 2.
This install also carries extra NCBI-sourced databases built locally in `~/blastdb`
(PDB proteins, RefSeq viral proteins, 16S rRNA, fungi ITS, mitochondrion and viral
genomes — about 1 GB of sources, built with `makeblastdb` because NCBI prebuilt
files do not open on Apple Silicon). They serve local `blastp`/`blastn` searches
when a workflow names them; `tblastn`/`blastx` still need the real NCBI choice.
WhatsApp outbound delivery waits for Meta business verification, so the website is the entry point today.
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
User accounts for teams are not in the tool, and the single login user guards the demo.
The decision record for the local tool direction is `docs/decisions/008-local-tool-own-server.md`.
