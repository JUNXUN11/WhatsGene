"""Agent loop (PRD §4.1): plan -> run step -> observe -> next step.

Every decision is persisted to the step log with its reason. The loop
counts every BLAST submission against the per-job budget (config) and,
on exhaustion, stops and reports what was and was not found. Recovery
is defined behaviour: next candidate on failed verification, one
adjusted-settings retry on too-few hits — never improvised retries.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Callable

from . import agent, config, db, rules_engine
from .blast_backend import BlastBackend, BlastNotWired
from .classify import classify_hits
from .validate import ValidationError, detect_type, looks_like_accession, normalise_sequence
from .verify import coverage_from_coordinates, verify_candidate

Milestone = Callable[[dict, str], None]


def _log(job_id: str, **kw) -> None:
    db.add_step(job_id, **kw)


def _with_coverage(hits: list[dict], query_length: int) -> list[dict]:
    out = []
    for hit in hits:
        enriched = dict(hit)
        if "query_coverage" not in enriched and "query_start" in enriched and "query_end" in enriched:
            enriched["query_coverage"] = coverage_from_coordinates(
                query_start=enriched["query_start"], query_end=enriched["query_end"],
                query_length=query_length)
        out.append(enriched)
    return out


def process_job(job: dict, backend: BlastBackend,
                on_milestone: Milestone | None = None) -> dict:
    """Run one job through the loop. Returns the final job row."""
    job_id = job["id"]
    started = time.monotonic()
    deadline = datetime.now(timezone.utc) + timedelta(seconds=config.MAX_JOB_SECONDS)
    db.update_job(job_id, status="running", deadline_at=deadline.isoformat())
    searches_used = 0

    def notify(message: str) -> None:
        if on_milestone:
            try:
                on_milestone(db.get_job(job_id) or job, message)
            except Exception:
                pass  # notification failure never fails the job (ARCHITECTURE)

    def budget_left() -> bool:
        return searches_used < config.MAX_SEARCHES_PER_JOB and (time.monotonic() - started) < config.MAX_JOB_SECONDS

    raw = (job.get("raw_input") or "").strip()
    question = job.get("question", "")

    # --- accession resolution ---
    sequence = ""
    accession: str | None = None
    query_annotation = ""
    if looks_like_accession(raw):
        accession = raw.upper()
        try:
            record = backend.fetch_by_accession(accession)
        except BlastNotWired as exc:
            _log(job_id, step="fetch_accession", observation=f"Accession {accession}",
                 decision="fail job", reason=str(exc))
            return db.update_job(job_id, status="failed", input_kind="accession",
                                 accession=accession, error=str(exc)) or job
        sequence = (record.get("sequence") or "").upper()
        query_annotation = record.get("annotation", "") or record.get("organism", "")
        _log(job_id, step="fetch_accession", observation=f"{accession} -> {len(sequence)} residues",
             decision="use fetched sequence", reason="Accession resolved via BLAST backend (E-utilities).")
    else:
        raw_sequence = raw
        # WhatsApp messages may carry "SEQUENCE <question>" in one text; the
        # stored raw_input is sequence-only by the time the loop runs, except
        # dev API calls which pass sequence and question separately.
        try:
            sequence, _header = normalise_sequence(raw_sequence)
        except ValidationError as exc:
            _log(job_id, step="validate", observation="Sequence input", decision="fail job", reason=str(exc))
            return db.update_job(job_id, status="failed", error=str(exc)) or job

    # --- validate + detect ---
    try:
        detected = detect_type(sequence)
    except ValidationError as exc:
        _log(job_id, step="validate", observation=f"Sequence length {len(sequence)}",
             decision="fail job", reason=str(exc))
        return db.update_job(job_id, status="failed", sequence=sequence,
                             query_length=len(sequence), error=str(exc)) or job
    _log(job_id, step="validate", observation=f"{detected} sequence, {len(sequence)} residues",
         decision="accept input", reason="Alphabet and length checks passed (blast-rules §2).")

    # --- intent -> rules engine (-> logged deviation hook) ---
    intent = agent.get_intent(question)
    choice = rules_engine.choose_search(intent=intent, detected_type=detected)
    _log(job_id, step="choose_search",
         observation=f"intent goal={intent.get('goal')}, target={intent.get('target_organism')}, detected={detected}",
         decision=f"{choice['program']} / {choice['database']}",
         reason=f"{choice['reason']} [{choice['rule']}]")
    deviation = agent.propose_deviation(intent=intent, detected_type=detected, rules_choice=choice)
    applied_deviation = False
    if deviation:
        applied = bool(config.DEVIATION_AUTO_APPLY)
        _log(job_id, step="deviation", observation=f"Rules choice {choice['program']}/{choice['database']}",
             decision=("apply deviation" if applied else "keep rules choice"),
             reason=deviation.get("reason", ""), is_deviation=True,
             deviation_reason=deviation.get("reason", ""))
        if applied:
            choice = {**choice, "program": deviation["program"], "database": deviation["database"],
                      "reason": choice["reason"] + f" Deviation applied: {deviation.get('reason', '')}"}
            applied_deviation = True

    parameters: dict = {
        "evalue_threshold": 0.01,
        "word_size": 3 if detected == "protein" else 11,
        "matrix": "BLOSUM62" if detected == "protein" else None,
        "rationale": choice["reason"],
        "rule": choice["rule"],
        "deviation_applied": applied_deviation,
    }
    db.update_job(job_id, sequence=sequence, query_length=len(sequence), detected_type=detected,
                  input_kind="accession" if accession else f"fasta_{detected}",
                  accession=accession, intent=intent, program=choice["program"],
                  database=choice["database"], organism_filter=choice.get("organism_filter"),
                  parameters=parameters)
    notify(f"Job {job_id} started: {choice['program']} against {choice['database']}.")

    # --- search / classify / verify loop ---
    hits: list[dict] = []
    verification: dict | None = None
    outcome: str | None = None
    retried = False

    while True:
        if not budget_left():
            _log(job_id, step="budget", observation=f"searches_used={searches_used}",
                 decision="stop searching", reason="Run budget exhausted (max searches or max time).")
            outcome = outcome or "incomplete_budget"
            break
        kind = "retry" if retried else "primary"
        try:
            rid = backend.submit(sequence=sequence, program=choice["program"],
                                 database=choice["database"],
                                 parameters={**parameters, "kind": kind})
        except BlastNotWired as exc:
            _log(job_id, step="submit", observation=f"{choice['program']} / {choice['database']}",
                 decision="fail job", reason=str(exc))
            summary = f"Search could not be submitted. {exc}"
            return db.update_job(job_id, status="failed", searches_used=searches_used,
                                 summary=summary, error=str(exc)) or job
        searches_used += 1
        db.create_search(job_id, kind=kind, program=choice["program"],
                         database=choice["database"], parameters=parameters, rid=rid)
        db.update_job(job_id, searches_used=searches_used)
        _log(job_id, step="submit", observation=f"RID {rid} ({kind})",
             decision="poll for results", reason="BLAST job submitted via backend interface.")
        try:
            status = backend.poll(rid)
            if status != "ready":
                _log(job_id, step="poll", observation=f"RID {rid} status={status}",
                     decision="fail search", reason="BLAST job did not complete.")
                outcome = "incomplete_budget"
                break
            raw_hits = backend.fetch_results(rid)
        except BlastNotWired as exc:
            _log(job_id, step="poll", observation=f"RID {rid}", decision="fail job", reason=str(exc))
            return db.update_job(job_id, status="failed", searches_used=searches_used, error=str(exc)) or job

        hits = classify_hits(_with_coverage(raw_hits, len(sequence)))
        counts: dict[str, int] = {}
        for hit in hits:
            counts[hit["classification"]] = counts.get(hit["classification"], 0) + 1
        _log(job_id, step="classify", observation=f"{len(hits)} hits: {counts}",
             decision="verify candidates in rank order",
             reason="Classification in deterministic code (blast-rules §7 thresholds).")
        notify(f"Job {job_id}: {len(hits)} hits classified.")

        candidates = [h for h in hits if h["classification"] in ("strong", "borderline")]
        confirmed = False
        for candidate in candidates:
            if not budget_left():
                _log(job_id, step="budget", observation=f"searches_used={searches_used}",
                     decision="stop verification", reason="Run budget exhausted during verification.")
                break
            try:
                recip_rid = backend.submit(
                    sequence=str(candidate.get("sequence", sequence)), program=choice["program"],
                    database=choice["database"],
                    parameters={**parameters, "kind": "reciprocal",
                                "candidate_accession": candidate.get("accession", "")})
            except BlastNotWired as exc:
                _log(job_id, step="reciprocal", observation=candidate.get("accession", "?"),
                     decision="fail job", reason=str(exc))
                return db.update_job(job_id, status="failed", searches_used=searches_used,
                                     hits=hits, error=str(exc)) or job
            searches_used += 1
            db.create_search(job_id, kind="reciprocal", program=choice["program"],
                             database=choice["database"], parameters=parameters, rid=recip_rid)
            db.update_job(job_id, searches_used=searches_used)
            reciprocal_hits = classify_hits(_with_coverage(backend.fetch_results(recip_rid), len(sequence)))
            verification = verify_candidate(
                candidate=candidate, reciprocal_hits=reciprocal_hits,
                query_accession=accession, query_length=len(sequence),
                query_annotation=query_annotation)
            _log(job_id, step="verify",
                 observation=f"Candidate {candidate.get('accession', '?')} ({candidate['classification']}, E={candidate.get('evalue')})",
                 decision=("confirmed" if verification["confirmed"] else "not confirmed — try next candidate"),
                 reason="; ".join(verification["reasons"]))
            if verification["confirmed"]:
                outcome = "confirmed"
                confirmed = True
                break
        if confirmed:
            break
        if verification is not None:
            outcome = "not_confirmed"

        if outcome is None:
            outcome = "not_confirmed"
        # Too-few recovery: exactly one adjusted-settings retry, logged.
        significant = counts.get("strong", 0) + counts.get("borderline", 0)
        if significant == 0 and not retried and budget_left():
            retried = True
            parameters = {**parameters, "evalue_threshold": 0.1, "adjusted_retry": True}
            db.update_job(job_id, parameters=parameters)
            _log(job_id, step="retry", observation="No strong/borderline hits",
                 decision="retry with adjusted settings",
                 reason="Too-few-hits playbook (blast-rules §6): loosened E-value threshold to 0.1.")
            continue
        break

    summary = agent.summarise(job=db.get_job(job_id) or job, hits=hits,
                              outcome=outcome, verification=verification)
    final = db.update_job(job_id, status="done", outcome=outcome, hits=hits,
                          summary=summary, searches_used=searches_used)
    _log(job_id, step="summarise", observation=f"outcome={outcome}",
         decision="report to user", reason="Summary generated from parsed facts only.")
    notify(f"Job {job_id} done ({outcome}). {summary}")
    return final or job
