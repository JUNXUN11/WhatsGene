# WhatsGene

**BLAST for people who don't use BLAST every day.** Paste a sequence or accession, ask in plain words, and get a verified verdict, with the exact E-value, identity, and coverage behind it. Everything runs on your own machine, against your own databases.

Built for the Meta Global AI Developer Hackathon, track **Build for Your World**, with **Muse Spark** (Meta Model API) or **Muse Spark Open** (open weights).

```bash
git clone https://github.com/JUNXUN11/WhatsGene.git ~/WhatsGene && cd ~/WhatsGene && ./start
```

## The problem

A wet-lab biologist runs BLAST a few times a year, and every run feels like the first one. Which of the five programs? Which database? Is E = 1e-5 good enough? Was the hit verified? The public NCBI queue can also take minutes to hours. Mistakes here give a wrong biological answer, not just a slow one.

## What WhatsGene does

- **Picks the search for you.** A rules engine in code chooses the program (blastp, blastn, tblastn, blastx) and the database from your query type and question.
- **Runs locally in seconds.** BLAST+ runs against your own databases: SwissProt (575k proteins), PDB, RefSeq viral, 16S rRNA, fungal ITS, mitochondrial genomes, or custom databases you build in the app. A typical search finishes in 4–30 s.
- **Verifies, doesn't just list.** Each hit is classified strong, borderline, or not significant by fixed thresholds in code. The top hit must pass reciprocal-best-hit, coverage, length, and annotation checks before WhatsGene says "confirmed".
- **Shows its work.** Every workflow stores the program, database, exact parameters, hits, and a step log with the reason for each decision. Short peptides get the NCBI short-query profile automatically (E 200000, word 2, PAM30), shown beside the defaults.
- **Goes further when you need it.** Fan-out runs every applicable program at once. MAFFT alignment and a neighbor-joining tree come from confirmed homologs. Any workflow can switch to the real NCBI BLAST service.
- **Fits a lab.** A one-line install, a first-run setup wizard that downloads and builds the database, and owner-managed accounts with private workflows per person. `./start --share` serves the whole lab network.

## How Meta's models are used

The core rule: **Muse explains, code computes.** The model never picks a program, decides significance, or produces a number.

- **Reads your question.** Muse turns free text such as "does a worm have anything like this?" into a structured intent: the goal, a target organism, and open points. Code validates every field, and the rules engine still picks the program from it.
- **Writes the verdict.** After the search, Muse writes the plain-language summary from the stored facts. A number guard checks every number Muse writes against the stored results. One invented or changed value, and WhatsGene shows the code-written summary instead.
- **Grounded Ask.** On every results page, Muse answers follow-up questions from the stored results only, under the same number guard, and the page labels each answer as Muse or stored. If the stored results can't answer, it says so. Per-user quotas, an answer cache, and a kill switch keep it safe to run.
- **Setup assistant.** In Settings, Muse explains the local BLAST setup plan in your own terms, while code runs and proves every step.
- **MCP tools.** An MCP server exposes `run_search`, `get_workflow`, `explain_workflow`, `sort_files`, `build_custom_database`, `build_database_from_taxon`, and more. A model agent can sort a folder of messy files, build a database from it, and run a verified search, all through the same audited code paths.

Paste a key in Settings → Muse AI and every workflow uses it. Muse connects through any OpenAI-compatible endpoint: the Meta Model API, Modal, Baseten, or your own hardware. Every call is logged, times out in 20 s during a search, and has a deterministic fallback, so the tool still works offline.

## Try it

After install, the browser opens at `http://127.0.0.1:8000`. Create your account, then press **Run setup now** (Settings → Local BLAST setup). Then try:

| Input | Question | Database (More options) |
|---|---|---|
| `P68871` | Identify this protein | default: confirmed in about 5 s, E 6.6e-106 |
| `PNLHGLFGRKTG` | (Single, blastp) | default: short-query profile applied |
| `P0DTC2` | Find related viral proteins | `refseq_viral_protein` |
| `NR_102783.2` | Identify this bacterium | `16s_rrna` |
| `NC_045512.2` | Identify this virus | `refseq_viral_genomic` |
| `NM_006744.4:84-689` | Identify this protein | Real NCBI BLAST: a CDS slice searched on NCBI |

You need macOS or Linux, Git, Python 3.12+, Node 20+, and NCBI BLAST+ (`brew install blast`). MAFFT (`brew install mafft`) is optional and makes alignments local. Start again later with `cd ~/WhatsGene && ./start`.

## Under the hood

| Layer | What |
|---|---|
| Backend | Python, FastAPI, SQLite; a background worker runs workflows in parallel |
| Search | BLAST+ locally; NCBI URL API and E-utilities for remote searches |
| Science | Rules engine, classifier, and verifier in plain code; thresholds in config, never in prompts |
| Frontend | Nuxt, served by the backend from one address (`./start`) |
| Agent | Muse Spark Open over an OpenAI-compatible API; MCP server over stdio |
| Tests | 201 offline tests, covering the textbook cases (globin, insulin, RBP4, the Lab 04 short query, the CDS subrange) |

## What leaves your machine

In local mode, nothing. Each of these is opt-in and labelled on the results page: the real NCBI choice (sends the sequence to NCBI), an accession that isn't in your databases (only the ID goes to NCBI, to fetch the sequence), alignment without local MAFFT (EBI), and Ask (stored facts go to your Muse endpoint).

## Built during the hackathon

Everything in this repository was written during the building period: the first commit is on 29 Oct 2026, and the commit history shows the work day by day. It uses the open-source BLAST+, MAFFT, Biopython, FastAPI, and Nuxt, and the public SwissProt, NCBI RefSeq, and taxonomy data.

WhatsGene is for research and education. It does not give medical advice. MIT License, see `LICENSE`.
