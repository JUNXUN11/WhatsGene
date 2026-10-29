## Goal

Build WhatsGene for the Meta Global AI Developer Hackathon (building period Oct 27 – Nov 4, submission Nov 4, 9:00 PM ET) as a solo developer. WhatsGene is a verifiable, multimodal bioinformatics agent on WhatsApp with a web report companion. A student or junior dry-lab researcher starts work by voice, text, FASTA file, or gel photo, WhatsGene runs instant sequence analysis and watches long NCBI BLAST jobs in the background, then notifies the researcher on WhatsApp with a verified summary when the result is ready — so they stop refreshing their PC. Tagline: *Don't watch your BLAST run. WhatsGene watches it for you.* Primary track: Build for Your World. Secondary flags: Best Agentic Use-Case, Best Build on Meta Open Weight Models, Best Creative Build.

## The Pain

Bioinformatics work is waiting work. A BLAST search at NCBI, and similar database or pipeline jobs, can take far longer than expected. The researcher gets a Request ID or a queued job, keeps a laptop open, and checks the result page again and again. Existing tools return raw tables when the job finally finishes; they do not push a short, explained, verified summary to the phone the researcher always carries. WhatsGene removes the watching: submit once, close the laptop, get a WhatsApp message when it is done, already summarised.

## Success Criteria

- A public live web app accepts a FASTA or raw DNA sequence and returns GC content, ORF and protein translation, and primer candidates with Tm/GC in under 60 seconds for demo sequences. *E. coli* codon optimisation with old-vs-new comparison is included only if the BLAST core is stable.
- A BLAST job submitted from WhatsApp or web returns a Job ID immediately, is polled in the background without the user staying online, and on completion sends a WhatsApp notification with a verified 5-line summary plus a link to the full web report.
- The BLAST summary always shows: program chosen and why, database searched, top hit organism and accession, identity %, query coverage, bit score, and E-value. No summary number exists without a raw NCBI result behind it.
- Every result shows tool provenance: which analysis step ran, its raw output, and which model explained it. No result is LLM-only text.
- A verifier pass from Muse Spark Open on Baseten either confirms the primary result or flags a specific discrepancy that is shown to the user.
- WhatsApp is two-way multimodal, not output-only: it receives text, voice note, FASTA document, and gel photo, and it replies with text summary, Muse Image diagram, and report link (plus spoken summary only if a voice-output path is confirmed on Day 0).
- Submission package is complete: public GitHub repo with README, live web link, WhatsApp demo in a 3-minute video, and a clear `For research and education only. Not medical advice.` label. No medical diagnosis, no basic RAG, no simple image analyser, no generic tutor chatbot.

## Multimodal Journey

WhatsApp is the full front door: multimodal in, long agent work in the middle, multimodal out. Each modality causes the next step; none is decoration. The single WhatsApp thread is the product story judges see.

| Modality | Direction | Muse model | Job |
|---|---|---|---|
| Voice note | In | Muse Voice Transcribe | Give the instruction hands-free, in Malay or English |
| Text / FASTA file | In | Muse Glimmer | Validate DNA vs RNA, detect language, start the job |
| Gel photo | In | SAM 3.1 | Segment bands and estimate band position |
| Instant + BLAST tools | Middle | Muse Spark | Plan steps, run tools, submit and watch NCBI BLAST |
| Verification | Middle | Muse Spark Open | Confirm or flag the summary against raw hits |
| Text + diagram | Out | Muse Spark + Muse Image | WhatsApp summary with report diagram attached |
| Interactive visual | Out (web) | Muse Wonder | DNA-to-protein report visual linked from WhatsApp |

Connected demo story: (1) Student sends a voice note: *"BLAST this sequence and design primers."* (2) Student sends the FASTA file in the same chat. Instant GC/ORF/primer results return at once, and the BLAST job is submitted with a Job ID. (3) Student closes the laptop. WhatsGene polls NCBI in the background. (4) WhatsApp notification arrives: BLAST done, verified, with top hit, E-value, and diagram. (5) Back in lab, student sends a gel photo in the same chat; SAM 3.1 checks whether the band matches the PCR product size WhatsGene predicted from its primers.

## BLAST Workflow

Grounded in UTM SECB2103 Bioinformatics I, Topic 04 — BLAST (Dr Haslina Hashim): BLAST is a local-alignment search with three phases (list/compile, scan, extend / trace-back), judged by bit score and E-value. WhatsGene automates the lecture's 4 NCBI steps and explains each choice instead of exposing NCBI's raw form.

**Step 1 — Specify the sequence.** Accept FASTA text, raw sequence, FASTA document, or an accession-style request. Validate alphabet (DNA A/T/G/C or protein), length, and format before any job is submitted. Bad input fails here with a clear WhatsApp message, never as a wasted NCBI job.

**Step 2 — Select the BLAST program automatically.** The agent picks the program from query and database type and states why in the summary. The user can override by voice or text.

| Program | Query | Database | Typical use in WhatsGene |
|---|---|---|---|
| blastn | DNA | DNA | Identify a nucleotide sequence |
| blastp | Protein | Protein | Identify a translated ORF |
| blastx | DNA (6-frame translation) | Protein | Unknown DNA that may code a known protein |
| tblastn | Protein | DNA (6-frame translation) | Find unannotated coding regions |
| tblastx | DNA (6-frame) | DNA (6-frame) | Last-resort translated comparison; slowest, off by default |

**Step 3 — Select the database.** Default to a bounded, fast database choice for the demo (for example a RefSeq/nucleotide subset appropriate to the program) and name the exact database in every summary. Full large-database searches are allowed but labelled as longer-wait jobs before submission, with an honest Job ID and no promised finish time.

**Step 4 — Set parameters with sensible defaults, explained.** Defaults the agent sets and can explain in simple English: E-value threshold, word size, substitution matrix for protein searches (BLOSUM62 as in the lecture examples), filtering/compositional adjustment, organism limit when the user names one, and max target sequences. The lecture's insulin example (E-value shifting from 0.05 to 0.09 to 1e-04 when filtering and compositional settings change) is the teaching point: WhatsGene shows which settings were used, so a changed result is never a mystery.

**Reading the result.** The report ranks hits and explains significance: bit score (higher = stronger alignment, comparable across searches), E-value (expected number of chance hits; smaller = more significant), identity %, and query coverage. A top hit with a weak E-value or low coverage is flagged as weak, never presented as a confident identification.

**Too many / too few hits playbook.** If a job returns too many hits, WhatsGene suggests and can apply: lower the E-value threshold, limit by organism, or reduce max target sequences. If too few or none: raise the E-value threshold, check filtering, consider blastx for a divergent coding sequence, or widen the database. This suggestion is generated from the actual hit count and raw output, then verified before sending. Multidomain caution from the lecture (HIV-1 Pol case): a hit covering only part of the query is reported as partial-domain evidence, not whole-protein identity.

## BLAST Watch — Async Notification

This is the hero feature and the reason WhatsApp is necessary, not decorative.

1. **Submit.** User submits from WhatsApp or web. WhatsGene submits to NCBI BLAST, stores Job ID (Request ID), query hash, program, database, parameters, user channel, and start time, then replies at once: *"Job #WG-123 is running. You can close your laptop. I will message you here when it is done."*
2. **Watch.** A background poller checks job status at a respectful interval, with backoff. The user does not need to stay online, keep the web page open, or send any further message. Job state (queued, running, done, failed, expired) is visible on the web report page for the same Job ID.
3. **Retrieve and parse.** On completion, WhatsGene fetches the raw result itself and parses the hit table: accession, organism, identity %, coverage, bit score, E-value, alignment length. Raw output is stored and linked as proof.
4. **Summarise.** Muse Spark writes the 5-line WhatsApp summary from parsed hits only, following the Reading-the-result rules above, plus one next-step suggestion when the too-many/too-few playbook applies.
5. **Verify.** Muse Spark Open receives the raw top hits and the draft summary and returns confirm-or-flag. A flagged summary is corrected or sent with the flag shown; it is never silently sent as confirmed.
6. **Notify.** WhatsApp message arrives in the same thread: done notice, verified summary, Muse Image diagram, and full report link. Within 24 hours of the user's last message this is a normal reply; for longer jobs, a pre-approved WhatsApp utility template (*"Your WhatsGene job {{1}} is done"*) opens the conversation and the summary follows. Failed or expired jobs also notify, with the reason and a one-tap resubmit instruction. No silent failures.

Demo honesty: BLAST wait time is not controllable. The 3-minute video submits a real job early, then shows a separate real job (submitted before recording, labelled on screen with its Job ID and wait time) completing and triggering the notification on camera. No fake completion is presented as live.

## Approach

Build the web core first as the safety net, then add WhatsApp as a second channel on the same backend agent. One Python API owns agent orchestration, sequence tools, NCBI BLAST submission and polling, a persistent job store, Muse model calls, and WhatsApp webhook handling. One web frontend owns sequence input, live agent progress, job status, results, and the downloadable report. WhatsApp never has separate logic; it formats the same agent result for chat and links to the web report. Muse models are tiered so the core ships even if a creative layer slips: Tier 1 is Muse Spark plus Muse Spark Open plus instant sequence tools plus BLAST Watch; Tier 2 is SAM 3.1 gel check plus Muse Voice Transcribe; Tier 3 is Muse Glimmer routing plus Muse Image and Muse Wonder visuals. Muse Code is the build accelerator and is credited in the README and video, not presented as a product feature.

## Key Decisions

- **Name:** WhatsGene. Short, instantly explains WhatsApp + gene, easy to say in the demo and to share as a WhatsApp contact. Tagline: *Don't watch your BLAST run. WhatsGene watches it for you.* Working name only until final checks on GitHub, X, and domain registrars are done (no major bioinformatics product was found using this name; a parked `whatsgene.com` domain exists).
- **Track and framing:** Build for Your World, domain = bioinformatics education and dry-lab research in Malaysia. Rejected: Push the Frontier as primary, because the personal-domain and WhatsApp distribution story is stronger for Impact (30%).
- **Channel:** Dual channel, web first and WhatsApp second on one backend, with WhatsApp as the primary notification channel. Rejected: WhatsApp-only, because a public production number needs business verification and display-name review with no guaranteed timeline, while the Cloud API test number only reaches allow-listed recipients. Rejected: web-only, because it loses the Meta-app distribution, the multimodal phone demo, and the push notification that is the core value. Instagram DM is rejected for the MVP: it needs a professional account linked to a Page and heavier messaging review, and is weaker for documents and report links; it can be a later sharing surface for Muse Image/Wonder visuals.
- **Core job split:** Instant tools (GC, ORF, primers) for the immediate reply, plus one long job (NCBI BLAST Watch) for the notification story. Rejected for MVP: codon optimisation as a headline feature (kept only as a stretch item), live multi-database BLAST fan-out, RNA folding, human codon optimisation, accounts, and payments, because each adds latency or scope a solo dev cannot validate in 9 days.
- **Verification:** Muse Spark is the primary planner/explainer and Muse Spark Open on Baseten (`meta-models/muse-spark-open-1026` per the Participant Guide) is the verifier. Baseten documents Muse Spark Open as always reasoning, which suits a shown verification trace. Rejected: single-model self-check, because judges reward verifiable agents and the Open Weights bonus needs an eligible open-weight build.
- **Bioinformatics engine:** Sequence representation and translation use Biopython `Bio.Seq`. Primer design is a bounded Python step reporting Tm and GC. BLAST is executed by NCBI, never simulated by the LLM; WhatsGene submits, polls, parses, and explains the real NCBI output. Rejected: local BLAST against a toy database presented as NCBI-equivalent; any local fallback must be labelled as a demo database with its size stated.
- **SAM 3.1 job:** Segment bands in an uploaded gel electrophoresis photo and compare estimated band position against the predicted PCR product size from the chosen primers. Rejected: generic species-from-photo identification, because it reads as a banned simple image analyser and does not close the design-to-lab loop.
- **Voice job:** Muse Voice Transcribe converts WhatsApp voice notes to agent instructions and notes. A spoken reply is included only if Day 0 confirms a Muse voice output path; otherwise the WhatsApp reply is text plus report link and no TTS claim is made. Rejected: assuming an unverified TTS endpoint.
- **Visual job:** Muse Image generates the report ORF/primer diagram and Muse Wonder generates the interactive DNA-to-protein report visual, both labelled as concept visuals, never as real protein structure. Rejected: presenting generated visuals as scientific evidence; all scientific claims come from tool output.

## Competitors and Differentiation

Existing tools are strong at single steps. WhatsGene wins on workflow, access, notification, and trust for beginners — not on claiming better science than specialist tools. Pitch line: *ORFfinder finds an ORF. Primer3 designs primers. NCBI makes you watch the BLAST page. WhatsGene does it in one WhatsApp thread, watches the long job for you, and proves the summary.*

- **NCBI BLAST web:** The reference BLAST service, with full program, database, and parameter control. The user must keep checking the result and then interpret a raw hit table alone. WhatsGene edge: same real NCBI engine, but agent-chosen program/parameters explained in simple English, background watching, and a verified WhatsApp summary with E-value and bit score interpreted.
- **NCBI ORFfinder:** Finds ORFs only; web version is limited to a subrange of the query sequence up to 50 kb. No primers, no BLAST, no beginner explanation. WhatsGene edge: full chained job and explained report from one input.
- **Primer3 / Primer3Plus:** Primer design only, with a parameter-heavy form that is hard for beginners. WhatsGene edge: agent sets sensible defaults, runs primers as one step in a larger job, and explains the result.
- **IDT Codon Optimization Tool:** Codon optimisation only, tied to a gene-synthesis ordering flow. WhatsGene edge: optimisation, if shipped, sits inside a complete analysis with old-vs-new diff and next-step report, no ordering funnel.
- **Sequence Manipulation Suite (SMS):** Many small DNA/protein programs, each on a separate page, with manual copy-paste between them. WhatsGene edge: one input, one agent run, one report; no manual chaining.
- **Galaxy:** Powerful, reusable workflow platform with free public servers, but it requires learning histories, tool names, and workflow concepts. WhatsGene edge: zero-install WhatsApp/web entry in under 60 seconds for a first result and a phone notification for long jobs; position as the front door, with export toward Galaxy when depth is needed.
- **Benchling:** Professional molecular biology suite (sequence design, primers, CRISPR, alignments, notebook and registry) and free for academics, but desktop-first and onboarding-heavy for a student with one FASTA file. WhatsGene edge: phone-first, voice-capable, Malay/English explanation. Honest boundary: WhatsGene is not a Benchling replacement; it is the fast first step before Benchling.
- **General AI chatbots:** Fluent sequence explanations, but numbers can be invented with no tool run behind them. WhatsGene edge: every number comes from a logged tool execution or a real NCBI result, Muse Spark Open verifies it, and SAM 3.1 can check a gel photo against the predicted PCR product.

Claims WhatsGene must never make: better primer accuracy than Primer3, better BLAST science than NCBI, more depth than Benchling or Galaxy, guaranteed BLAST finish times, or any medical interpretation. The defensible claim is: same trusted engines, radically lower friction, background watching with WhatsApp notification, multimodal phone access, and verifiable agent output.

## Steps

1. **Day 0 feasibility spike (half day). Gate before all other work.** Create the Meta app with the WhatsApp use case per the official get-started flow, generate a temporary token, send a test message, and stand up a webhook endpoint that echoes an inbound message. Make one successful call each to Muse Spark, Muse Voice Transcribe (including a WhatsApp `.ogg` voice note, converting format only if the call fails), SAM 3.1 on a sample gel photo, and Muse Spark Open on Baseten. Submit one real small NCBI BLAST job, record its Request ID, and confirm status polling works. Record pass/fail and latency for each. Cut any Tier 2/3 item that fails and keep Tier 1.
2. **Core sequence engine and job store (Day 1–2).** Python API endpoints: validate sequence (FASTA or raw, DNA or protein), compute length and GC, find ORFs and translate with Biopython, design bounded primer candidates with Tm/GC. Add a persistent job store (Job ID, query hash, program, database, parameters, channel, status, timestamps, raw result link) and a background poller with backoff. Ship bundled samples, including a dengue virus sequence and human insulin (lecture example accession NP_000198 for the protein flow). Log every step input and output for provenance display.
3. **BLAST Watch and verification (Day 2–3).** Implement the BLAST Workflow: automatic program selection with stated reason, database choice with wait warning for large databases, explained default parameters, NCBI submission, status polling, raw result parsing (accession, organism, identity %, coverage, bit score, E-value), Muse Spark 5-line summary under the Reading-the-result rules, too-many/too-few suggestion, and Muse Spark Open confirm-or-flag verification. Add the research/education-only guardrail and a refusal for personal medical interpretation requests.
4. **Web product (Day 3–4).** Five screens: input with sample buttons, live instant-analysis view with step log, job status page for BLAST Watch (queued/running/done/failed with elapsed time), results with sequence viewer, ORF table, primer cards, and BLAST hit table, and report with download. Deploy the web app and API on public HTTPS hosts so the WhatsApp webhook and judges share one URL.
5. **WhatsApp channel (Day 5–6).** Implement the Cloud API webhook: verify callback, receive text, voice, document, and image messages, download media, route voice through Muse Voice Transcribe and gel photos through SAM 3.1, run the same agent, reply instantly for instant tools, return a Job ID for BLAST, and send the completion notification in the same thread when the poller finishes. Prepare the utility template for jobs exceeding the 24-hour window. Create a permanent token via a System User instead of relying on the 24-hour temporary token. Keep the web flow fully usable if WhatsApp is unavailable.
6. **Multimodal and creative polish (Day 7).** Add Muse Glimmer fast routing for DNA-vs-RNA and English/Malay detection with report summary translation, Muse Image report diagram attached to the WhatsApp completion message, and Muse Wonder interactive visual linked from the report. Add the *E. coli* codon optimisation stretch item only now, and only if BLAST Watch is stable. Each item ships only if its Day 0 check passed and Tier 1–2 are stable; cut in this order: codon optimisation, Wonder, Image, Glimmer.
7. **Hardening and user validation (Day 8).** Test invalid sequences, empty input, BLAST failure/expiry notification, deliberately corrupted summary flagged by the verifier, and a medical-advice prompt refusal. Ask 5 UTM bioinformatics coursemates to run one sample each on web and WhatsApp, including one full BLAST Watch cycle; fix only blocking issues and capture one testimonial quote for the pitch.
8. **Submission (Day 9, before Nov 4, 9:00 PM ET).** Publish the public GitHub repo with README (setup, Muse model roles, BLAST Workflow, what was built during the hackathon, Muse Code credit), confirm the live web link works unauthenticated, record the 3-minute video on a real phone (voice note and FASTA in, instant result, real BLAST Job ID submitted, a labelled pre-submitted real job completing with WhatsApp notification on camera, gel photo check, verified report out), and post the demo to X for the Most Viral flag. Submit one team entry via the CV platform and verify repo and video links open publicly.

## Validation Plan

- **Day 0 gate evidence:** Logged successful calls for WhatsApp test message round-trip, Muse Spark, Muse Voice Transcribe, SAM 3.1, and Baseten Muse Spark Open, plus one real NCBI BLAST submission with a recorded Request ID and a successful status poll, each with timestamp and latency. Any failure triggers the tier cut in Step 1, not a workaround claim.
- **Sequence correctness:** Hand-check GC, ORF coordinates, and translation for both bundled samples against independent manual calculation on a short subsequence; primer Tm/GC recomputed by a second formula in the test. Expected: exact match on the short subsequence and no unexplained mismatch on full samples.
- **BLAST correctness:** For one bundled sample, compare WhatsGene's parsed top hit, identity %, bit score, and E-value field-by-field against the raw NCBI result for the same Request ID. Any mismatch fails the check. Summary numbers must trace to parsed raw output, not to model text.
- **Async notification evidence:** Submit a BLAST job, close the web page, and confirm the WhatsApp completion message arrives without any further user action, with correct Job ID and a working report link. Repeat with a forced failed/expired job and confirm the failure notification arrives with a resubmit instruction.
- **Verifier evidence:** Run one deliberately corrupted tool output and one deliberately corrupted BLAST summary and confirm Muse Spark Open flags both and the UI/WhatsApp output shows the flag. A silent pass on corrupted input fails this check.
- **WhatsApp end-to-end:** From a real phone, send each of text sequence, voice note, FASTA document, and gel photo to the test number and confirm the correct response type for each (instant summary, Job ID then notification, or gel check). Repeat the text flow on the web app and confirm identical tool outputs.
- **Guardrail check:** Submit a personal diagnosis-style prompt and an invalid non-DNA sequence; expected: refusal or validation error with the research/education label, and no medical interpretation.
- **Submission check:** Open the GitHub repo and live app in a private browser window with no login, play the full video, and confirm all links resolve before submitting.

## Risks / Open Questions

- **WhatsApp production access is the highest risk.** Business verification and display-name review may not finish by Nov 4. Mitigation is structural: the test number proves the channel in the video and the public web app is the judge-testable product. Never claim public WhatsApp availability unless a real number is approved and tested.
- **BLAST wait time is outside our control.** NCBI queue time varies and results can expire. Mitigation: honest Job ID with no promised finish time, respectful polling with backoff, failure/expiry notification with resubmit, bounded default database for demos, and the labelled pre-submitted job in the video. Never present a cached or local result as a live NCBI completion.
- **Long jobs can cross the WhatsApp 24-hour window.** Mitigation: design for the utility template in Step 5 from the start, and test the over-window path with a forced delay before submission day.
- **Token and media handling can break the demo.** Temporary tokens expire and WhatsApp voice arrives as `.ogg`. Mitigation: permanent System User token before Day 6 ends, and the Day 0 transcribe test on a real WhatsApp voice file.
- **Full Muse stack can cause scope creep for a solo dev.** Mitigation: tier order in the Approach, cut order in Step 6, and the Day 0 gate. Tier 1 (instant tools + BLAST Watch + verification) alone is a submittable product.
- **Generated visuals could be misread as science.** Mitigation: concept-visual labelling in Key Decisions; SAM band comparison and all numeric claims come only from tool or NCBI output.
- **Name clearance is not final.** WhatsGene had no major bioinformatics product in a quick search, but GitHub, X, trademark, and domain checks must be completed on Day 0 before branding is printed everywhere.
- Open questions: None blocking. The spoken-reply item is conditional on the Day 0 voice-output check and is removed, not assumed, if unconfirmed.

## Sources

- UTM SECB2103 Bioinformatics I, Topic 04 — BLAST (Dr Haslina Hashim): 4-step NCBI workflow, program selection (blastn/blastp/blastx/tblastn/tblastx), databases, parameters (E-value, word size, BLOSUM62, filtering, organism limit), local-alignment phases, bit score and E-value interpretation, too-many/too-few strategy, HIV-1 Pol multidomain case. Local lecture file supplied by the participant.
- https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started
- https://developers.facebook.com/documentation/business-messaging/whatsapp/about-the-platform
- https://docs.baseten.co/inference/model-apis/reasoning
- https://docs.baseten.co/inference/model-apis/overview
- https://biopython.org/docs/latest/api/Bio.Seq.html
- https://www.ncbi.nlm.nih.gov/orffinder/
