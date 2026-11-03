# WhatsGene — 3-minute demo script

Website-first demo (WhatsApp outbound is gated by Meta business
verification; see the honest note at the end). Start both servers first:

```bash
cd backend && .venv/bin/python -m uvicorn app.main:app --port 8000   # SEARCH_BACKEND=local
cd frontend && npm run dev                                          # http://localhost:3000
```

## Script

1. **Landing (0:00–0:30).** Open http://localhost:3000. Pitch: “BLAST for
   people who don't use BLAST every day. Queue the search; read a verified
   answer, not a hit list.” Point at the status line: queued → running →
   done, every search storing its parameters.
2. **Parallel queue (0:30–1:00).** Submit three workflows back-to-back:
   - `P68871` — “Identify this protein” — Auto.
   - `PNLHGLFGRKTG` — Lab 04 short query — Single, blastp.
   - `P68871` — “Identify this protein” — Run all.
   Open **Workflows**: all three running side by side. Nobody refreshes
   NCBI; the worker watches.
3. **Rich context result (1:00–1:50).** Open the globin result: top hit
   P68873, E-value 6.56e-106, strong, reciprocal verification confirmed —
   plus *why* blastp was chosen and the exact parameters. Open the Lab 04
   result: E-value cutoff **200,000**, word size **2**, **PAM30**,
   labelled short-query adjusted next to the defaults (10 / 3 / BLOSUM62).
   Show the failed tblastn row in the fan-out: stored with its reason,
   never hidden.
   Then open the **real NCBI** workflow you started before recording
   (see Before recording): `NM_006744.4:84-689`, the RBP4 CDS, sliced to
   bases 84–689 in code and searched with blastn against
   `refseq_nucleotide` on NCBI's own servers. The data notice says the
   sequence went to NCBI; the step log shows the NCBI request ID.
4. **Ask (1:50–2:20).** In the Ask box: “What is the E-value cutoff?”
   (quotes 200,000), “Compare the programs” (per-program top hits).
   Then ask something unanswerable (“What is the weather?”) — it refuses
   from stored results. That refusal is the anti-hallucination story.
5. **MSA → tree (2:20–2:50).** On the confirmed globin job, click
   **Build MSA + tree**: MAFFT alignment and neighbor-joining tree
   (Poisson, complete deletion) appear, with the decisions in the step
   log. With `mafft` installed (`brew install mafft`) this takes seconds;
   without it the EBI service took 141 s in our check, so build the tree
   before recording and only show the finished result.
6. **Close (2:50–3:00).** “Same trusted engines, radically lower
   friction. Every number on screen came from a logged tool run.”

## Before recording

Start the real NCBI workflow 10–15 minutes before you record, because
the primary search and each reciprocal check wait in NCBI's queue:
New search → `NM_006744.4:84-689`, question `Identify this protein`,
More options → search location **Real NCBI BLAST** → Run.

## Backup

If live BLAST misbehaves on recording day, use an already-finished job
from the Workflows list and say so on camera (“pre-run this morning,
same code path”). Never present a recorded fixture result as a live
search: Fixture jobs say so in their data notice.

## Honest WhatsApp note (say only if asked)

WhatsApp inbound is proven live (a real phone message created a
confirmed job end-to-end). Outbound replies are currently blocked by
Meta business verification on the test account (`131031` — account
restricted until verified), so the shipped demo is website-first.
WhatsApp is retried after this; Telegram is the fallback channel.
