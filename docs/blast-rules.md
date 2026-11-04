# BLAST Rules — Source of Truth for Science

> **Source:** SECB2103 Bioinformatics I, Topic 04 — BLAST (Dr Haslina Hashim, UTM), based on Pevsner, *Bioinformatics and Functional Genomics* 3e, Ch. 4. The 64-slide lecture deck is course material and is not in this repository. Referenced by `docs/PRD.md` v0.3 §3–§4. **Do not change without owner approval; record any change in the PRD change table.** Thresholds here are implemented in code/config only — never in model prompts. The model interprets and explains; the rules engine chooses the search; code classifies and verifies.

## Source map — pages and figures used

| Lecture item | B&FG 3e page | Used for |
|---|---|---|
| Fig. 4-1 BLASTP web search overview | 123 | Overall submit → results flow |
| Fig. 4-2 / Fig. 4-3, Tables 4-1, 4-2 | 124–125 | Database choice; DNA six-frame translation |
| Fig. 4-4 Insulin parameter example | 128 | Step 4 parameters; E-value sensitivity (see §4) |
| Figs. 4-5 to 4-10 | 129–135 | Output formatting, graphic summary, hit list |
| Fig. 4.11 Word list / neighbourhood (w=3, T=11) | 116 / 138 | How BLAST works — compile phase |
| Fig. 4-12 / 4-13 Threshold T and word size | 139–140 | Word size defaults (see §5) |
| Fig. 4-14 Extreme value distribution | 141 | E-value statistics (see §5) |
| Fig. 4-15 Search strategies overview | 143–145 | Strategy selection |
| Fig. 4-16 RBP4 → RefSeq search | 147 | Weak-hit caution |
| Fig. 4-17 Reciprocal search RBP4 / CG8 | 149 | Reciprocal confirmation rule (§8) |
| Fig. 4-18 HIV-1 Pol domain graphic | 151 | Multidomain caution (§9) |
| Figs. 4-19 to 4-24 HIV-1 Pol follow-ups | 153–158 | Taxonomy report; human/bacterial Pol searches |
| Find-a-Gene project (closing slides) | — | Core WhatsGene use case (§10) |

Full slide outline: Introduction → Step 1 Specify sequence → Step 2 Select program → Step 3 Select database → Step 4 Select parameters/formatting → Stand-alone BLAST+ → Algorithm (list / scan / extend, E-value, bit score, E↔p) → Strategies (significance, too many/few hits, HIV-1 Pol multidomain) → Find-a-Gene → Perspective.

---

## 1. Rules engine — intent + input type → program and database

This mapping is deterministic code (PRD §3). The model supplies only the structured intent (goal, target organism/group, anything unclear) from the user's free text; it does not choose the program directly.

| Detected input | Intent / target | Program | Database (default) |
|---|---|---|---|
| Protein | Identify the protein | `blastp` | RefSeq protein |
| Protein | Find the gene in another organism/group (DNA or ESTs), e.g. beta globin → nematodes | `tblastn` | EST or nucleotide for the target group |
| DNA | Identify the nucleotide sequence | `blastn` | RefSeq nucleotide |
| DNA | Unknown DNA that may code for a known protein | `blastx` | RefSeq protein |
| Protein/DNA | No fitting row above | least-translated program that fits (below) | matching type |

Rules: prefer the least-translated program that answers the question (protein + protein DB → `blastp`, never `tblastx` by default; `tblastx` is off unless no other program fits). Database type must match the program (protein DB for `blastp`/`blastx`; nucleotide/EST for `blastn`/`tblastn`); default to a bounded, fast, named database and print its exact name. A named organism/group in the intent becomes the organism filter. Large `nr`/`nt` searches are labelled "longer wait" with no promised finish time.

**Deviations:** the model may propose a different program/database only with a stated reason. The proposal, reason, and whether it was applied are logged and shown to the user and on the results page (whether it applies automatically or needs confirmation: PRD Open questions #7). The rules engine's original choice is never silently overwritten.

## 2. STEP 1 — Specify the sequence of interest

*Step 1 of the NCBI 4-step workflow. WhatsGene must fail bad input here and never submit a wasted NCBI job. In the product, a WhatsApp message containing a sequence or accession starts the job; its accompanying text is the intent source.*

**Accepted input:** FASTA text (DNA or protein), raw sequence string, or an NCBI accession (e.g. `NP_000509`, `NP_000198`). If an accession is given, fetch the sequence via NCBI E-utilities (Entrez) before any BLAST submission and record the resolved accession, organism, and length as provenance.

**Validation (deterministic code, not the model):**
- Strip FASTA header (`>...`) and whitespace/line breaks; reject empty input.
- Detect alphabet: DNA if the sequence uses only A/C/G/T (allow U→T for RNA, N for ambiguous) above a high proportion; otherwise treat as protein (20 standard amino-acid letters). Ambiguous/mixed input → specific error naming the offending characters/positions.
- Reject characters outside the detected alphabet, sequences too short to search meaningfully, and malformed FASTA (header without sequence). The error says what is wrong and what to paste instead — never a generic "invalid input".
- Record query length, detected type (DNA/protein), and a hash of the normalised sequence on the job for reproducibility.

## 3. STEP 2 — Select the BLAST program

The rules engine (§1) selects from query type × database type:

| Program | Query | Database | Translation | Use when |
|---|---|---|---|---|
| `blastn` | DNA | DNA | 1× | Identify a nucleotide sequence against nucleotide DB |
| `blastp` | Protein | Protein | 1× | Identify a protein / translated ORF against protein DB |
| `blastx` | DNA | Protein | 6-frame query | Unknown DNA that may code for a known protein |
| `tblastn` | Protein | DNA | 6-frame database (36 comparisons) | Find unannotated coding regions in DNA/ESTs |
| `tblastx` | DNA | DNA | 6×6 frames | Last resort only; slowest — **off by default** |

DNA is translatable in six reading frames (3 forward, 3 reverse — Fig. 4-3).

## 4. STEP 3/4 — Database and parameters

Database defaults and organism filtering follow §1. Parameters the system sets, records, and must be able to explain:

| Parameter | Default / rule |
|---|---|
| E-value threshold | Set explicitly per search; reported on the results page. The submission threshold is not the significance verdict (§7). |
| Word size | Protein `w=3`; nucleotide typically 11 (7 = more sensitive/slower, 15 = faster/fewer hits); megaBLAST 28 if ever used (Fig. 4-13). |
| Substitution matrix | `BLOSUM62` for protein searches (lecture default). |
| Filtering / masking | NCBI defaults unless overridden; **always record the setting used**. |
| Max target sequences | Bounded default; record the value. |
| Organism limit | From intent if named; otherwise none. |

**Why settings are always shown (Fig. 4-4, p.128):** BLASTP of human insulin (`NP_000198`) against a *C. elegans* RefSeq database gives E ≈ 0.05 with conditional compositional adjustment, E ≈ 0.09 with no adjustment, and E ≈ 1e-04 with composition-based statistics — filtering/composition alone moves the same hit across significance boundaries. Every results page therefore prints program, database, matrix, E-threshold, word size, filtering, and organism limit.

---

## 5. How BLAST works (for explanations, not for reimplementation)

WhatsGene calls NCBI BLAST through the BLAST backend interface; it never reimplements or simulates it. Three phases (Altschul et al. 1990), for the summary explainer:

1. **Compile (list):** break the query into words of length `w` (protein `w=3`) and list neighbourhood words scoring ≥ threshold `T` (BLASTP default `T=11`).
2. **Scan:** scan the database for word matches, then extend promising hits.
3. **Extend / trace-back:** extend and trace back to produce the gapped local alignment.

Lower `T` → more word hits and extensions (more sensitive, slower). Scores follow an extreme value distribution, not a normal distribution (Fig. 4-14).

### Transcription — lecture p.48 figure block (BLAST statistics)

> **E-value:** "The expect value E is the number of alignments with scores greater than or equal to score S that are expected to occur by chance in a database search." Key equation: **E = K·m·n·e^(−λS)**, where S = score, m,n = sequence lengths, λ,K = Karlin–Altschul parameters. E decreases exponentially as S increases; for E = 1, one match of that score is expected by chance, and E scales with database size.
>
> **Bit score:** raw scores depend on matrix and database, so they are normalised: **S′ = (λS − ln K) / ln 2**, with **E = m·n·2^(−S′)**. Bit scores are comparable across different searches and matrices; higher bit score = stronger alignment.
>
> **E ↔ p:** **p = 1 − e^(−E)**. For small E, p ≈ E (E=0.001 → p≈0.001; E=0.05 → p≈0.0488); for E=1 → p≈0.632, E=10 → p≈0.99995. E-values in the 1–10 range are far easier to read than the corresponding p-values, which is why WhatsGene reports E.

## 6. Agent-loop search adjustments (within budget)

The loop acts on observed, classified results only, logs the reason for every action, and counts every search against the job budget (PRD §4.1). It never retries silently.

- **Too many hits:** tighten — stricter E-threshold, apply/tighten the organism limit, or fewer max target sequences.
- **Too few / no significant hits:** loosen — raise the E-threshold, check filtering is not masking real signal, consider `blastx` for a divergent coding sequence, or widen the database. Each retry states which setting changed and why.
- **Candidate not confirmed (§8):** drop it and try the next-ranked candidate while budget remains.
- **Budget out:** stop and report what was found and what was not. No further searches.

## 7. Reading results — significance classification

Every hit carries: accession, organism, % identity, query coverage, alignment length, bit score, and E-value — all parsed from raw NCBI output. No summary or follow-up number may exist without a raw result behind it.

**Query coverage is computed in code from hit coordinates:** `coverage % = (query_end − query_start + 1) / query_length × 100` for the hit's high-scoring pair. It is never taken from model text.

**Implementation thresholds (initial defaults — tune only in code/config, traceable to this section):**

| Class | Rule (all conditions on the parsed hit) | Meaning shown to user |
|---|---|---|
| **Strong** | E ≤ 1e-5 **and** query coverage ≥ 70% | Very unlikely by chance; covers most of the query |
| **Borderline** | 1e-5 < E ≤ 1e-2, **or** E ≤ 1e-5 with 30% ≤ coverage < 70% | Possible relative — needs verification (§8) before any claim |
| **Not significant** | E > 1e-2, **or** coverage < 30% regardless of E | Treat as noise / partial-domain only; never present as an identification |

Notes: (a) these cut-offs are WhatsGene implementation choices derived from the lecture's E-value interpretation — E ≪ 0.01 is treated as significant, E near 1–10 as chance-level — not a single number quoted from the deck, because the deck teaches interpretation, not one universal cutoff; database drift means tests check behaviour, not exact hits. (b) A high-E, low-identity hit (lecture Fig. 4-16 RBP4 example) is flagged weak, never presented as confident. (c) Classification is deterministic code; the model only words the explanation and must cite E-value, identity, coverage.

## 8. Verification module (deterministic code)

Applied to candidates in rank order (top Strong first, then best Borderline). A candidate is **confirmed** only if all applicable checks pass; otherwise it is **not confirmed** with the specific failing check recorded, and the loop tries the next candidate (§6).

1. **Reciprocal best hit:** search the candidate's sequence back against the original query's database/organism. Confirmed requires the original query (or same gene/protein family) as a top hit with a significant E-value (lecture Fig. 4-17, p.149: human RBP4 finds CG8; reciprocal BLASTP with CG8 recovers RBP4 and other lipocalins → true positive).
2. **Query coverage:** from hit coordinates (§7). Low coverage fails whole-protein claims even when E is significant — partial-domain evidence only (§9).
3. **Length mismatch:** compare query and subject lengths. A large mismatch is recorded as a failure reason (checks from Fig. 4-17: very different lengths, non-significant E, missing family motif, subject not annotated in the family). Any numeric cut-off lives in code/config, not in this prose and not in prompts.
4. **Annotation check:** the subject's annotation must be consistent with the query's gene/protein family; an unrelated annotation fails confirmation with that reason.

## 9. Multidomain caution

A hit covering only part of the query is **partial-domain evidence**, not whole-protein identity (HIV-1 Pol, Figs. 4-18/4-19: bacterial matches split by retropepsin / reverse transcriptase / RNase H / integrase domains). Always report coverage alongside identity so a domain-only match cannot read as a full-length homolog.

## 10. Find-a-Gene pattern and Tier 2 escalation

**Find-a-Gene (core demo):** start from a known protein and discover a homolog in another organism — query `NP_000509` (human beta globin) → `tblastn` against nematode EST database → candidate novel globin → confirm with `blastx` and the §8 verification module. The headline question — *"human beta globin (NP_000509): is there a related gene in nematodes, and how confident can I be?"* — must run exactly this pattern.

**Weak-hit escalation (Tier 2, in order after Tier 1):** when no candidate reaches Strong, or all candidates fail verification, escalate to PSI-BLAST within the same budget and logging rules — **only after verifying NCBI's web API supports it**; if it does not, record that in PRD Open questions and keep Tier 1 behaviour. After confirmation, confirmed homologs go to MSA and a neighbor-joining tree. MSA/phylogeny rules are **not** in this file and must not be invented: they come from course decks 06 and 07 when provided.

## 11. Eval harness — textbook cases (behaviour, not exact hits)

Default suite runs offline on recorded NCBI responses (fixtures); the live suite is optional. Each case checks behaviour:

| Case | Expected behaviour |
|---|---|
| Beta globin `NP_000509` vs nematodes | Rules engine chooses `tblastn` (protein → EST/nucleotide target); a globin candidate is classified from parsed values and put through §8 verification |
| Insulin `NP_000198` vs *C. elegans* | Program/database choice is correct and the recorded settings are shown, because filtering/composition moves this hit's E-value (§4) |
| RBP4 vs CG8 | Weak/high-E hits are classified Borderline or Not significant and rejected as false positives unless §8 reciprocal, length and annotation checks confirm them |

Score is reported in the README at submission (PRD §10).

## 12. Follow-up grounding

Follow-up answers (WhatsApp) use only stored job results and this file, quoting actual E-value, identity and coverage. If the stored results cannot answer the question, the answer says so — the model must not fill gaps from general knowledge or invent values.
