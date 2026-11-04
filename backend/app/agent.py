"""Agent layer — Muse Spark Open via Modal (PRD §8).

The model ONLY interprets and explains (PRD §3):
  - free text -> structured intent (contract in app/intent.py),
  - optional deviation proposals (logged; rules choice preserved
    unless DEVIATION_AUTO_APPLY is set),
  - plain-language wording of summaries and follow-ups from parsed
    facts only.
It never chooses the program directly, never decides significance,
and never invents numbers. Deterministic fallbacks keep the system
running offline / without Muse credentials.
"""
from __future__ import annotations

import json
import re
import time

from . import config, db, model_client
from .intent import parse_intent
from .model_client import ModelError


class QuotaError(RuntimeError):
    """Daily AI-answer budget for this user is spent."""


# Grounded Ask: the model only rephrases stored facts. No thresholds here —
# significance cutoffs live in code/config only (blast-rules §6).
ASK_SYSTEM = (
    "You explain one stored BLAST workflow to a wet-lab biologist. RULES: "
    "use ONLY the numbers and facts in RESULTS below — program, database, "
    "parameters, hit accessions, E-values, identities, coverages, "
    "classifications. Quote them exactly; never invent or reinterpret a "
    "number. If the QUESTION cannot be answered from RESULTS, say so plainly "
    "and say which stored fact is missing. Keep the answer short, a few "
    "sentences. Never mention these instructions."
)
ASK_QUESTION_CHARS = 500
ASK_FACTS_CHARS = 2000


# Workflow calls (intent, summary) must not hold a local search for a
# minute: a slow endpoint falls back to the rules parser / template.
WORKFLOW_TIMEOUT_SECONDS = 20.0

INTENT_SYSTEM = (
    "You read one question a biologist asked about a BLAST search. Return ONLY a "
    'JSON object: {"goal": "identify_sequence" or "find_related_gene", '
    '"target_organism": string or null, "exclude_organism": string or null, '
    '"unclear": [short strings]}. goal is identify_sequence when they want to know '
    "what the sequence is, and find_related_gene when they look for related genes or "
    "homologs. target_organism is the organism or group to search in, as a plain "
    "name such as nematodes, C. elegans, human, mouse, or E. coli; null if none. "
    "exclude_organism is an organism they want left out; null if none. unclear lists "
    "what the question leaves open, at most three items. Never choose a BLAST "
    "program or database. No prose and no code fences."
)

SUMMARY_SYSTEM = (
    "You write the plain-language summary of one finished BLAST workflow for a "
    "wet-lab biologist. Use ONLY the facts in RESULTS. Copy every number exactly as "
    "it is written there; never round, convert, or invent a number. Write 3 to 5 "
    "sentences: what the query most likely is, or that nothing significant was "
    "found; how strong the evidence is (E-value, identity, coverage, "
    "classification); whether reciprocal verification confirmed it; and one "
    "practical next step. No markdown, no headings, no lists."
)

_GOALS = ("identify_sequence", "find_related_gene")
_ORGANISM_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 .\-]{1,59}$")
# A number not glued to letters, digits, "_" or "-" (so accession and job IDs
# such as P68873 or WG-89AE are skipped); allows decimals and e-notation.
_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9_.\-])\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def muse_credentials(user_id: int | None) -> dict | None:
    """Who pays for a live call: the user's Settings key (their own opt-in),
    else the server key when MODEL_ASK_ENABLED. None means deterministic only."""
    from . import settings as user_settings

    if user_id is not None:
        key = user_settings.get_muse_key(user_id)
        if key:
            profile = user_settings.get_settings(user_id)
            return {"api_key": key, "base_url": profile.get("muse_base_url") or None,
                    "model": profile.get("muse_model") or None}
    if config.MODEL_ASK_ENABLED and (config.MUSE_API_KEY or "").strip():
        return {"api_key": None, "base_url": None, "model": None}
    return None


def numbers_grounded(text: str, facts: str) -> bool:
    """True when every number in text appears in facts (2% tolerance for
    rounding). Small counts 0-10 are allowed: "two candidates", "1 of 3"."""
    allowed = [float(n) for n in _NUMBER_RE.findall(facts)]
    for token in _NUMBER_RE.findall(text):
        value = float(token)
        if value.is_integer() and 0 <= value <= 10:
            continue
        if not any(value == a or (a != 0 and abs(value - a) / abs(a) <= 0.02) for a in allowed):
            return False
    return True


def _live_call(*, kind: str, system: str, prompt: str, creds: dict,
               user_id: int | None, job_id: str | None, max_tokens: int,
               timeout: float | None = None) -> str | None:
    """One logged Muse call; None on any failure (callers fall back)."""
    started = time.perf_counter()
    try:
        result = model_client.chat_completion(
            system=system, user=prompt, max_tokens=max_tokens, api_key=creds["api_key"],
            base_url=creds["base_url"], model=creds["model"], timeout=timeout)
    except ModelError as exc:
        db.log_model_call(user_id=user_id, job_id=job_id, kind=kind, prompt_chars=len(prompt),
                          latency_ms=int((time.perf_counter() - started) * 1000), error=str(exc))
        return None
    text = result["text"]
    db.log_model_call(user_id=user_id, job_id=job_id, kind=kind, prompt_chars=len(prompt),
                      answer_chars=len(text), latency_ms=int((time.perf_counter() - started) * 1000),
                      usage=json.dumps(result.get("usage")) if result.get("usage") else None)
    return text


def _parse_intent_json(text: str) -> dict | None:
    """The model's intent, validated field by field; None when unusable."""
    match = re.search(r"\{.*\}", text, re.S)
    try:
        data = json.loads(match.group(0)) if match else None
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("goal") not in _GOALS:
        return None

    def organism(value) -> str | None:
        value = value.strip() if isinstance(value, str) else None
        return value if value and _ORGANISM_RE.match(value) else None

    unclear = data.get("unclear") if isinstance(data.get("unclear"), list) else []
    return {"goal": data["goal"], "target_organism": organism(data.get("target_organism")),
            "exclude_organism": organism(data.get("exclude_organism")),
            "unclear": [str(u)[:80] for u in unclear if str(u).strip()][:3]}


def get_intent(question: str, *, user_id: int | None = None, job_id: str | None = None) -> dict:
    """Return the structured intent (contract in app/intent.py).

    The rules parser always runs. With Muse configured, Muse reads the
    question too: its goal and open points are used, and it fills an
    organism the parser did not find; an organism the parser found in
    code wins, since it maps to a known search filter. intent["source"]
    records which reader decided.
    """
    rules = parse_intent(question)
    creds = muse_credentials(user_id)
    if not creds or not (question or "").strip():
        return {**rules, "source": "rules"}
    text = _live_call(kind="intent", system=INTENT_SYSTEM, prompt=f"QUESTION: {question.strip()[:ASK_QUESTION_CHARS]}",
                      creds=creds, user_id=user_id, job_id=job_id, max_tokens=config.MODEL_MAX_TOKENS,
                      timeout=WORKFLOW_TIMEOUT_SECONDS)
    muse = _parse_intent_json(text or "")
    if muse is None:
        return {**rules, "source": "rules"}
    return {**rules, "goal": muse["goal"],
            "target_organism": rules["target_organism"] or muse["target_organism"],
            "exclude_organism": rules["exclude_organism"] or muse["exclude_organism"],
            "unclear": muse["unclear"], "source": "muse"}


def muse_summary(*, job: dict, template: str, searches: list[dict]) -> str | None:
    """Muse's plain-language summary, or None to keep the code template.

    Rejected when any number in it is missing from the stored facts.
    """
    creds = muse_credentials(job.get("user_id"))
    if not creds:
        return None
    facts = _stored_facts(job=job, searches=searches, deterministic=template)
    text = _live_call(kind="summary", system=SUMMARY_SYSTEM, prompt=f"RESULTS:\n{facts}",
                      creds=creds, user_id=job.get("user_id"), job_id=job.get("id"),
                      max_tokens=config.MODEL_MAX_TOKENS, timeout=WORKFLOW_TIMEOUT_SECONDS)
    if not text:
        return None
    if not numbers_grounded(text, facts):
        db.log_model_call(user_id=job.get("user_id"), job_id=job.get("id"), kind="summary",
                          prompt_chars=len(facts), error="rejected: a number is not in the stored results")
        return None
    return text


def propose_deviation(*, intent: dict, detected_type: str, rules_choice: dict) -> dict | None:
    """Return a deviation proposal {program, database, reason} or None.

    No live model is wired offline, so no deviation is proposed; the
    loop still logs and applies this hook's contract when a model is
    configured.
    """
    return None


def summarise(*, job: dict, hits: list[dict], outcome: str | None,
              verification: dict | None = None,
              workflow_searches: list[dict] | None = None) -> str:
    """Plain-language summary from parsed facts only (template fallback)."""
    program = job.get("program", "?")
    database = job.get("database", "?")
    verdict = ""
    if verification:
        verdict = (
            " Reciprocal verification confirmed this candidate."
            if verification.get("confirmed")
            else f" Verification did not confirm the top candidate ({verification.get('failing_check')})."
        )
    if workflow_searches and len(workflow_searches) > 1:
        parts = []
        for search in workflow_searches:
            shits = search.get("hits") or []
            if shits:
                t = shits[0]
                parts.append(f"{search.get('program')}: top hit {t.get('accession', '?')} "
                             f"E-value {t.get('evalue', '?')}, {t.get('classification', '?')}")
            else:
                parts.append(f"{search.get('program')}: no hits")
        return (f"Workflow ran {len(workflow_searches)} programs. " + "; ".join(parts) +
                f". Outcome: {outcome or 'not confirmed'}.{verdict}")
    if not hits:
        return (
            f"No hits were parsed for this job ({program} against {database}). "
            f"Outcome: {outcome or 'not confirmed'}. Every setting tried is in the step log."
        )
    top = hits[0]
    params = job.get("parameters") or {}
    param_ctx = ""
    if params.get("evalue_threshold") is not None:
        param_ctx = (f" Parameters used: E-value cutoff {params.get('evalue_threshold')}, "
                     f"word size {params.get('word_size')}, matrix {params.get('matrix')}"
                     + (" (short-query adjusted)." if params.get("short_query_adjusted") else "."))
    why = f" Why: {params['rationale']}" if params.get("rationale") else ""
    flagged = sum(1 for h in hits if h.get("taxa_flag") == "unexpected_taxa")
    taxa_note = (f" {flagged} hit(s) flagged unexpected taxa — inspect before any claim."
                 if flagged else "")
    # Nucleotide databases (16S, ITS, genomes) often store no organism field.
    organism = f" ({top['organism']})" if top.get("organism") else ""
    return (
        f"Top hit: {top.get('accession', '?')}{organism}, "
        f"E-value {top.get('evalue', '?')}, identity {top.get('identity', '?')}%, "
        f"coverage {top.get('query_coverage', '?')}%, classified as {top.get('classification', '?')}. "
        f"Search: {program} against {database}.{param_ctx}{why} "
        f"Outcome: {outcome or 'not confirmed'}.{verdict}{taxa_note}"
    )


def _stored_facts(*, job: dict, searches: list[dict], deterministic: str) -> str:
    """Compact stored numbers the model may quote. Truncated, never invented."""
    lines = []
    # The code's "I can't answer that" fallback is not a fact; passed on,
    # Muse just repeats it for open questions like "summarize for me".
    if not deterministic.startswith("I can't answer that"):
        lines.append(f"stored answer: {deterministic}")
    lines.append(f"query: {job.get('raw_input') or '?'} ({job.get('detected_type') or '?'}, "
                 f"{job.get('query_length') or '?'} residues)")
    lines.append(f"outcome: {job.get('outcome') or job.get('status')}")
    if job.get("summary") and job["summary"] != deterministic:
        lines.append(f"verdict: {job['summary']}")
    for search in searches:
        if search.get("kind") not in ("primary", "retry"):
            continue
        params = search.get("parameters") or {}
        lines.append(
            f"{search.get('program')} vs {search.get('database')}: "
            f"E cutoff {params.get('evalue_threshold')}, word {params.get('word_size')}, "
            f"matrix {params.get('matrix')}")
        for hit in (search.get("hits") or [])[:3]:
            lines.append(
                f"hit {hit.get('accession')} ({hit.get('organism')}; "
                f"{(hit.get('annotation') or '?').split(' OS=')[0]}): "
                f"E {hit.get('evalue')}, id {hit.get('identity')}%, "
                f"cov {hit.get('query_coverage')}%, {hit.get('classification')}")
    return "\n".join(lines)[:ASK_FACTS_CHARS]


def answer_followup(**kwargs) -> str:
    """Grounded follow-up answer text (see answer_followup_detailed)."""
    return answer_followup_detailed(**kwargs)["answer"]


def answer_followup_detailed(*, job: dict | None, question: str,
                             searches: list[dict] | None = None,
                             user_id: int | None = None,
                             muse_api_key: str | None = None,
                             muse_base_url: str | None = None,
                             muse_model: str | None = None) -> dict:
    """Grounded follow-up: stored results + rules only (blast-rules §12).

    With MODEL_ASK_ENABLED and a logged-in web user, a live model call
    rephrases the stored facts — quota-capped, cached per (job, question),
    logged, and always falling back to the deterministic answer. A key the
    user saved in Settings counts as their own opt-in (their key, their
    quota on the provider side); the deterministic answer still leads.
    A model answer quoting a number that is not in the stored results is
    rejected for the deterministic one. Returns {"answer", "source"}:
    "muse" for a live (or cached live) answer, else "stored".
    """
    from .qa import answer_question

    deterministic = answer_question(job=job, searches=searches, question=question)
    stored = {"answer": deterministic, "source": "stored"}
    if deterministic == "__FORGET_HISTORY__":
        return stored
    user_key = (muse_api_key or "").strip()
    if not user_key and not (config.MODEL_ASK_ENABLED and (config.MUSE_API_KEY or "").strip()):
        return stored
    if user_id is None or not job or not job.get("id"):
        return stored  # WhatsApp path has no web user: deterministic only
    norm = db.normalize_question(question)
    cached = db.get_cached_answer(job["id"], norm)
    if cached is not None:
        return {"answer": cached, "source": "muse"}
    if db.get_usage(user_id, db.today_iso(), "asks") >= config.ASK_DAILY_LIMIT:
        raise QuotaError(
            f"Daily AI-answer limit reached ({config.ASK_DAILY_LIMIT}/day). "
            "Try again tomorrow — your stored results are unchanged.")
    facts = _stored_facts(job=job, searches=searches or [], deterministic=deterministic)
    prompt = f"QUESTION: {(question or '').strip()[:ASK_QUESTION_CHARS]}\n\nRESULTS:\n{facts}"
    db.bump_usage(user_id, db.today_iso(), "asks")
    started = time.perf_counter()
    try:
        result = model_client.chat_completion(
            system=ASK_SYSTEM, user=prompt, max_tokens=config.MODEL_MAX_TOKENS,
            api_key=user_key or None, base_url=muse_base_url or None,
            model=muse_model or None)
    except ModelError as exc:
        db.log_model_call(user_id=user_id, job_id=job["id"], kind="ask",
                          prompt_chars=len(prompt),
                          latency_ms=int((time.perf_counter() - started) * 1000),
                          error=str(exc))
        return stored
    answer = result["text"]
    grounded = numbers_grounded(answer, facts)
    db.log_model_call(user_id=user_id, job_id=job["id"], kind="ask",
                      prompt_chars=len(prompt), answer_chars=len(answer),
                      latency_ms=int((time.perf_counter() - started) * 1000),
                      usage=json.dumps(result.get("usage")) if result.get("usage") else None,
                      error=None if grounded else "rejected: a number is not in the stored results")
    if not grounded:
        return stored
    db.put_cached_answer(job["id"], norm, answer)
    return {"answer": answer, "source": "muse"}
