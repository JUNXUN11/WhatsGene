"""Agent loop: plan -> run step -> observe -> next step.

One job is one workflow. In auto mode the workflow is the rules engine's
single best search; in all mode it fans out to every BLAST program that
accepts the query type. Every search (primary, reciprocal, retry) is
stored with its exact parameters and hits, counts against the per-job
budget, and is logged with its reason. On budget exhaustion the loop
stops and reports what was and was not found.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone
from typing import Callable

from . import agent, config, db, rules_engine, settings as user_settings
from .blast_params import parameters_for
from .search_backend import NcbiRemote, SearchBackend, SearchError, local_database_name
from .classify import classify_hits, flag_unexpected_taxa
from .validate import ValidationError, detect_type, looks_like_accession, normalise_sequence, parse_accession_query
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


def _fetch_from_ncbi(accession: str) -> tuple[dict | None, str]:
    """Local mode fallback: fetch one accession through NCBI E-utilities.

    Only the accession ID goes to NCBI; the BLAST search itself stays on
    this machine. Returns (record, "") or (None, why it failed).
    """
    if not config.NCBI_EMAIL:
        return None, ("Set NCBI_EMAIL in backend/.env to fetch accessions from NCBI, "
                      "or paste the sequence itself.")
    try:
        return NcbiRemote().fetch_by_accession(accession), ""
    except SearchError as exc:
        return None, str(exc)


def process_job(job: dict, backend: SearchBackend,
                on_milestone: Milestone | None = None) -> dict:
    """Run one workflow through the loop. Returns the final job row."""
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
                pass  # notification failure never fails the job

    def budget_left() -> bool:
        return searches_used < config.MAX_SEARCHES_PER_JOB and (time.monotonic() - started) < config.MAX_JOB_SECONDS

    def cancelled() -> bool:
        fresh = db.get_job(job_id)
        return bool(fresh and fresh.get("status") == "cancelled")

    raw = (job.get("raw_input") or "").strip()
    question = job.get("question", "")

    # --- accession resolution ---
    sequence = ""
    accession: str | None = None
    query_annotation = ""
    query_organism: str | None = None
    accession_candidate, subrange = parse_accession_query(raw)
    if looks_like_accession(accession_candidate):
        accession = accession_candidate.upper()
        fetched_via = f"{backend.name} backend"
        try:
            record = backend.fetch_by_accession(accession)
        except SearchError as exc:
            record, ncbi_error = (_fetch_from_ncbi(accession) if backend.name == "local"
                                  else (None, ""))
            if record is None:
                error = f"{exc} {ncbi_error}".strip()
                _log(job_id, step="fetch_accession", observation=f"Accession {accession}",
                     decision="fail job", reason=error)
                return db.update_job(job_id, status="failed", input_kind="accession",
                                     accession=accession, error=error) or job
            fetched_via = "NCBI E-utilities (accession only; the search stays local)"
            _log(job_id, step="fetch_accession", observation=f"{accession} is not in the local databases",
                 decision="fetch the sequence from NCBI E-utilities",
                 reason="Only the accession ID is sent to NCBI; the BLAST search runs on this machine.")
        sequence = (record.get("sequence") or "").upper()
        if subrange is not None:
            start, end = subrange
            if not (1 <= start <= end <= len(sequence)):
                _log(job_id, step="fetch_accession", observation=f"{accession}:{start}-{end}",
                     decision="fail job",
                     reason=f"Subrange {start}-{end} is outside the fetched sequence (length {len(sequence)}).")
                return db.update_job(job_id, status="failed", input_kind="accession",
                                     accession=accession,
                                     error=f"Subrange {start}-{end} is outside {accession} (length {len(sequence)}).") or job
            sequence = sequence[start - 1:end]
            _log(job_id, step="fetch_accession",
                 observation=f"{accession} bases {start}-{end} -> {len(sequence)} bases (CDS slice)",
                 decision="use subrange sequence",
                 reason="Accession subrange applied in code (Lab 04 Q2 CDS pattern, blast-rules §11).")
        query_annotation = record.get("annotation", "") or record.get("organism", "")
        query_organism = (record.get("organism") or "").strip() or None
        organism_match = re.search(r"\[([^\]]+)\]\s*$", query_annotation)
        if organism_match:
            query_organism = organism_match.group(1)
        _log(job_id, step="fetch_accession", observation=f"{accession} -> {len(sequence)} residues",
             decision="use fetched sequence", reason=f"Accession resolved via {fetched_via}.")
    else:
        try:
            sequence, _header = normalise_sequence(raw)
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

    # --- intent -> workflow plan (rules engine; model supplies intent only) ---
    intent = agent.get_intent(question)
    mode = (job.get("workflow_mode") or "auto").lower()
    try:
        plan = rules_engine.plan_programs(
            intent=intent, detected_type=detected, mode=mode,
            requested_program=job.get("requested_program"),
            requested_database=job.get("requested_database"))
    except ValueError as exc:
        _log(job_id, step="choose_search", observation=f"mode={mode}",
             decision="fail job", reason=str(exc))
        return db.update_job(job_id, status="failed", sequence=sequence,
                             query_length=len(sequence), detected_type=detected,
                             intent=intent, error=str(exc)) or job
    choice = plan[0]
    _log(job_id, step="choose_search",
         observation=f"intent goal={intent.get('goal')}, target={intent.get('target_organism')}, detected={detected}",
         decision=f"{choice['program']} / {choice['database']}",
         reason=f"{choice['reason']} [{choice['rule']}]")
    if job.get("requested_database"):
        _log(job_id, step="database_choice",
             observation=f"User selected local database {job['requested_database']}",
             decision=f"search {choice['program']} / {choice['database']}",
             reason="Explicit database choice from the search form; "
                    "program and database type validated in code.")
    if len(plan) > 1:
        _log(job_id, step="plan_workflow",
             observation=f"mode={mode}: " + ", ".join(f"{p['program']}/{p['database']}" for p in plan),
             decision=f"run {len(plan)} searches in one workflow",
             reason="Fan-out requested; every program that accepts this query type runs "
                    "and stores its own parameters and hits for comparison.")
    deviation = agent.propose_deviation(intent=intent, detected_type=detected, rules_choice=choice) if mode == "auto" else None
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
            plan[0] = choice
            applied_deviation = True

    def recorded_db(database: str) -> str:
        """The database the search really ran on, for every stored record."""
        return local_database_name(database) if backend.name == "local" else database

    if backend.name == "local" and recorded_db(choice["database"]) != choice["database"]:
        _log(job_id, step="database_local", observation=f"Rules engine named {choice['database']}",
             decision=f"search the local {recorded_db(choice['database'])} copy",
             reason="LocalBlast serves this database from a local copy (decision 001); "
                    "results name the database actually searched.")

    def params_for_spec(spec: dict, kind: str) -> dict:
        base = parameters_for(program=spec["program"], detected_type=detected,
                              query_length=len(sequence),
                              organism_filter=spec.get("organism_filter"),
                              exclude_organism=spec.get("exclude_organism"))
        # Owner's Settings preset caps the submission threshold only;
        # significance classification (blast-rules §7) is unchanged.
        base = user_settings.apply_strictness(base, job.get("strictness"))
        return {"backend": backend.name, **base, "kind": kind,
                "rationale": spec["reason"], "rule": spec["rule"],
                "requested_database": job.get("requested_database"),
                "classification_cutoffs": job.get("cutoffs") or {"mode": "standard"},
                "deviation_applied": applied_deviation}

    primary_params = params_for_spec(choice, "primary")
    if subrange is not None and accession:
        primary_params["subrange"] = {"accession": accession, "start": subrange[0], "end": subrange[1]}
    if primary_params.get("short_query_adjusted"):
        _log(job_id, step="short_query",
             observation=f"{choice['program']} query length {len(sequence)}",
             decision=f"E-value cutoff {primary_params['evalue_threshold']:g}, word size "
                      f"{primary_params['word_size']}, matrix {primary_params['matrix']}",
             reason=primary_params.get("short_query_reason", "Short-query adjustment applied."))
    db.update_job(job_id, sequence=sequence, query_length=len(sequence), detected_type=detected,
                  input_kind="accession" if accession else f"fasta_{detected}",
                  accession=accession, intent=intent, program=choice["program"],
                  database=recorded_db(choice["database"]), organism_filter=choice.get("organism_filter"),
                  parameters=primary_params)
    notify(f"Job {job_id} started: {choice['program']} against {recorded_db(choice['database'])}.")

    # --- search / classify / verify across the planned programs ---
    primary_hits: list[dict] = []
    workflow_searches: list[dict] = []
    verification: dict | None = None
    outcome: str | None = None
    confirmed = False
    successful_searches = 0
    last_error: str | None = None

    def run_search(spec: dict, params: dict, kind: str) -> list[dict] | None:
        """Submit one search; store params+hits; return classified hits."""
        nonlocal searches_used, successful_searches, last_error
        if not budget_left():
            _log(job_id, step="budget", observation=f"searches_used={searches_used}",
                 decision="stop searching", reason="Run budget exhausted (max searches or max time).")
            return None
        try:
            rid = backend.submit(sequence=sequence, program=spec["program"],
                                 database=spec["database"], parameters=params)
        except SearchError as exc:
            search_id = db.create_search(job_id, kind=kind, program=spec["program"],
                                         database=recorded_db(spec["database"]), parameters=params, rid=None)
            db.complete_search(search_id, hits=[], status="failed", error=str(exc))
            _log(job_id, step="submit", observation=f"{spec['program']} / {recorded_db(spec['database'])}",
                 decision="skip this program, continue workflow", reason=str(exc))
            last_error = str(exc)
            return None
        searches_used += 1
        search_id = db.create_search(job_id, kind=kind, program=spec["program"],
                                     database=recorded_db(spec["database"]), parameters=params, rid=rid)
        db.update_job(job_id, searches_used=searches_used)
        _log(job_id, step="submit", observation=f"RID {rid} ({kind}, {spec['program']})",
             decision="poll for results", reason=f"BLAST job submitted via {backend.name} backend.")
        try:
            status = backend.poll(rid)
            if status != "ready":
                db.complete_search(search_id, hits=[], status="failed",
                                   error=f"BLAST job did not complete (status {status}).")
                _log(job_id, step="poll", observation=f"RID {rid} status={status}",
                     decision="fail search", reason="BLAST job did not complete.")
                return None
            raw_hits = backend.fetch_results(rid)
        except SearchError as exc:
            db.complete_search(search_id, hits=[], status="failed", error=str(exc))
            _log(job_id, step="poll", observation=f"RID {rid}", decision="fail search", reason=str(exc))
            last_error = str(exc)
            return None
        hits = flag_unexpected_taxa(
            classify_hits(_with_coverage(raw_hits, len(sequence)), job.get("cutoffs") or None),
            query_organism=query_organism or "", query_annotation=query_annotation)
        db.complete_search(search_id, hits=hits, status="done")
        successful_searches += 1
        counts: dict[str, int] = {}
        for hit in hits:
            counts[hit["classification"]] = counts.get(hit["classification"], 0) + 1
        _log(job_id, step="classify", observation=f"{spec['program']}: {len(hits)} hits: {counts}",
             decision="verify candidates in rank order",
             reason="Classification in deterministic code (blast-rules §7 thresholds).")
        notify(f"Job {job_id}: {spec['program']} returned {len(hits)} hits classified.")
        workflow_searches.append({"program": spec["program"], "database": spec["database"],
                                  "parameters": params, "hits": hits})
        return hits

    def verify_hits(spec: dict, base_params: dict, hits: list[dict]) -> dict | None:
        """Reciprocal verification for one program's candidates."""
        nonlocal searches_used
        result: dict | None = None
        for candidate in [h for h in hits if h["classification"] in ("strong", "borderline")]:
            if not budget_left():
                _log(job_id, step="budget", observation=f"searches_used={searches_used}",
                     decision="stop verification", reason="Run budget exhausted during verification.")
                break
            recip_params = {**base_params, "kind": "reciprocal",
                            "candidate_accession": candidate.get("accession", ""),
                            # Local organism scoping exists only for swissprot;
                            # elsewhere the searched database is the scope.
                            # Remote/fixture reciprocal searches keep targeting
                            # the query organism (blast-rules §8).
                            "organism_filter": (query_organism
                                                if backend.name != "local"
                                                or spec["database"] == "swissprot" else None)}
            try:
                recip_rid = backend.submit(
                    sequence=str(candidate.get("sequence", sequence)), program=spec["program"],
                    database=spec["database"], parameters=recip_params)
            except SearchError as exc:
                _log(job_id, step="reciprocal", observation=candidate.get("accession", "?"),
                     decision="try next candidate", reason=str(exc))
                continue
            searches_used += 1
            recip_id = db.create_search(job_id, kind="reciprocal", program=spec["program"],
                                        database=recorded_db(spec["database"]), parameters=recip_params, rid=recip_rid)
            db.update_job(job_id, searches_used=searches_used)
            if backend.poll(recip_rid) != "ready":
                db.complete_search(recip_id, hits=[], status="failed",
                                   error="Reciprocal search did not complete.")
                _log(job_id, step="reciprocal",
                     observation=f"Candidate {candidate.get('accession', '?')} RID {recip_rid}",
                     decision="try next candidate",
                     reason="Reciprocal search did not complete; verification cannot confirm this candidate.")
                continue
            reciprocal_hits = classify_hits(_with_coverage(backend.fetch_results(recip_rid), len(sequence)), job.get("cutoffs") or None)
            db.complete_search(recip_id, hits=reciprocal_hits, status="done")
            result = verify_candidate(
                candidate=candidate, reciprocal_hits=reciprocal_hits,
                query_accession=accession, query_length=len(sequence),
                query_annotation=query_annotation)
            _log(job_id, step="verify",
                 observation=f"Candidate {candidate.get('accession', '?')} ({candidate['classification']}, E={candidate.get('evalue')})",
                 decision=("confirmed" if result["confirmed"] else "not confirmed — try next candidate"),
                 reason="; ".join(result["reasons"]))
            if result["confirmed"]:
                break
        return result

    for index, spec in enumerate(plan):
        if cancelled():
            return db.get_job(job_id) or job
        params = params_for_spec(spec, "primary" if index == 0 else "primary")
        hits = run_search(spec, params, "primary")
        if hits is None:
            continue
        if index == 0:
            primary_hits = hits
        if not confirmed:
            found = verify_hits(spec, params, hits)
            if found is not None:
                verification = found
                if found["confirmed"]:
                    confirmed = True
                    outcome = "confirmed"

    if successful_searches == 0:
        summary = f"Search could not be submitted. {last_error or 'No search completed.'}"
        _log(job_id, step="submit", observation="all planned programs",
             decision="fail job", reason=summary)
        return db.update_job(job_id, status="failed", searches_used=searches_used,
                             summary=summary, error=last_error or summary) or job

    # Too-few recovery: exactly one adjusted retry of the primary search.
    significant = sum(1 for s in workflow_searches for h in s["hits"]
                      if h["classification"] in ("strong", "borderline"))
    if outcome is None:
        outcome = "confirmed" if confirmed else "not_confirmed"
    if significant == 0 and budget_left() and not cancelled():
        if primary_params.get("short_query_adjusted"):
            _log(job_id, step="retry", observation="No strong/borderline hits",
                 decision="no E-value retry",
                 reason="Short-query profile already uses the raised E-value cutoff "
                        "(Lab 04 Q1); loosening it again would only add noise.")
        else:
            retry_params = {**primary_params, "evalue_threshold": 0.1, "adjusted_retry": True, "kind": "retry"}
            db.update_job(job_id, parameters=retry_params)
            _log(job_id, step="retry", observation="No strong/borderline hits",
                 decision="retry with adjusted settings",
                 reason="Too-few-hits playbook (blast-rules §6): loosened E-value threshold to 0.1.")
            retry_hits = run_search(choice, retry_params, "retry")
            if retry_hits is not None:
                primary_hits = retry_hits
                if not confirmed:
                    found = verify_hits(choice, retry_params, retry_hits)
                    if found is not None:
                        verification = found
                        outcome = "confirmed" if found["confirmed"] else "not_confirmed"

    if not budget_left() and outcome == "not_confirmed" and significant == 0 and successful_searches:
        # Budget ran out before any confirmation could be established.
        fresh_counts = sum(1 for s in workflow_searches for h in s["hits"]
                           if h["classification"] in ("strong", "borderline"))
        if fresh_counts == 0 and searches_used >= config.MAX_SEARCHES_PER_JOB:
            outcome = "incomplete_budget"

    if cancelled():
        return db.get_job(job_id) or job
    final_params = {**primary_params,
                    "workflow": {"mode": mode, "searches": [
                        {"program": s["program"], "database": s["database"],
                         "parameters": s["parameters"], "hit_count": len(s["hits"])}
                        for s in workflow_searches]}}
    db.update_job(job_id, parameters=final_params)
    summary = agent.summarise(job=db.get_job(job_id) or job, hits=primary_hits,
                              outcome=outcome, verification=verification,
                              workflow_searches=workflow_searches)
    final = db.update_job(job_id, status="done", outcome=outcome, hits=primary_hits,
                          summary=summary, searches_used=searches_used)
    _log(job_id, step="summarise", observation=f"outcome={outcome}",
         decision="report to user", reason="Summary generated from parsed facts only.")
    notify(f"Job {job_id} done ({outcome}). {summary}")
    return final or job
