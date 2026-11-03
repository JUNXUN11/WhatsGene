"""Per-user customization profile — the no-code bridge for scientists.

Each install is single-user today (decision 007), but settings are stored
per user so a shared install later needs no migration. Scientists pick
plain-language options in the web UI; this module maps those choices to
exact code values.

Owner decision (009, amended): the strictness preset changes only the
*submission* E-value threshold — how many hits are collected. Hit
classification defaults to the course cut-offs (docs/blast-rules.md §7),
and a scientist may override them under "Custom cut-offs"; every job
snapshots the cut-offs it used and the results page records them, so a
custom label is never mistaken for the standard one. Verification gates
(reciprocal best hit, coverage floor in app/verify.py) stay standard.
Every number lives in code; nothing comes from a model prompt.

The Muse API key is stored in the same profile but is write-only over
the API: responses carry only whether a key is set and its last 4 chars.
It powers two features: the Settings setup assistant and workflow Ask.
"""
from __future__ import annotations

from typing import Any

from . import config, db

BACKEND_CHOICES = ("server", "local", "ncbi")
STRICTNESS_CHOICES = ("strict", "balanced", "loose")

# Submission E-value threshold per preset (blast-rules.md §4: the
# submission threshold is set explicitly per search and reported on the
# results page; it is not the significance verdict, §7).
#   strict   1e-5 — the §7 "strong" boundary; collects close matches only
#   balanced None — keep the rules-engine default (1e-2, blast_params.py)
#   loose    10   — the NCBI BLAST default (blast_params.NCBI_DEFAULTS);
#                   surfaces distant hits for inspection (Lab 04 Q3 style),
#                   which §7 still classifies as not significant
STRICTNESS_PRESETS: dict[str, dict[str, Any]] = {
    "strict": {
        "label": "Strict — close matches only",
        "evalue_threshold": 1e-5,
        "help": "Collect only hits at E ≤ 1e-5. Fast and clean; distant relatives may be missed.",
    },
    "balanced": {
        "label": "Balanced — recommended",
        "evalue_threshold": None,
        "help": "The standard WhatsGene cut-off (E ≤ 0.01). Right for most searches.",
    },
    "loose": {
        "label": "Loose — include distant hits",
        "evalue_threshold": 10.0,
        "help": "Collect hits up to E ≤ 10 so distant candidates can be inspected. "
                "They are still labelled “not significant” unless they pass the fixed science cut-offs.",
    },
}

def standard_cutoffs() -> dict[str, float]:
    """The course cut-offs (blast-rules.md §7) from config — the default."""
    return {
        "strong_max_evalue": config.STRONG_MAX_EVALUE,
        "strong_min_coverage": config.STRONG_MIN_COVERAGE,
        "borderline_max_evalue": config.BORDERLINE_MAX_EVALUE,
        "borderline_min_coverage": config.BORDERLINE_MIN_COVERAGE,
    }


DEFAULT_SETTINGS: dict[str, Any] = {
    "lab_name": "",
    "default_organism": "",
    "default_backend": "server",
    "strictness": "balanced",
    "cutoff_mode": "standard",
    "cutoffs": standard_cutoffs(),
    "muse_base_url": "",
    "muse_model": "",
}

_MAX_TEXT = 120
_MAX_KEY = 512


def _clean_cutoffs(raw: Any) -> dict[str, float]:
    """Validate custom cut-offs or raise ValueError with a plain message."""
    if not isinstance(raw, dict):
        raise ValueError("cutoffs must be an object.")
    try:
        cutoffs = {
            "strong_max_evalue": float(raw["strong_max_evalue"]),
            "strong_min_coverage": float(raw["strong_min_coverage"]),
            "borderline_max_evalue": float(raw["borderline_max_evalue"]),
            "borderline_min_coverage": float(raw["borderline_min_coverage"]),
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Cut-offs need numeric E-value and coverage values.") from exc
    if not (0 < cutoffs["strong_max_evalue"] <= cutoffs["borderline_max_evalue"] <= 10):
        raise ValueError("E-values must satisfy 0 < strong ≤ borderline ≤ 10.")
    if not (0 <= cutoffs["borderline_min_coverage"] <= cutoffs["strong_min_coverage"] <= 100):
        raise ValueError("Coverage must satisfy 0 ≤ borderline ≤ strong ≤ 100 (percent).")
    return cutoffs


def validate_settings(payload: dict[str, Any]) -> dict[str, Any]:
    """Clean a settings payload or raise ValueError with a plain message."""
    if not isinstance(payload, dict):
        raise ValueError("Settings must be an object.")
    lab_name = str(payload.get("lab_name") or "").strip()[:_MAX_TEXT]
    organism = str(payload.get("default_organism") or "").strip()[:_MAX_TEXT]
    backend = str(payload.get("default_backend") or "server").strip().lower()
    if backend not in BACKEND_CHOICES:
        raise ValueError("default_backend must be server, local, or ncbi.")
    strictness = str(payload.get("strictness") or "balanced").strip().lower()
    if strictness not in STRICTNESS_CHOICES:
        raise ValueError("strictness must be strict, balanced, or loose.")
    cutoff_mode = str(payload.get("cutoff_mode") or "standard").strip().lower()
    if cutoff_mode not in ("standard", "custom"):
        raise ValueError("cutoff_mode must be standard or custom.")
    cutoffs = (_clean_cutoffs(payload.get("cutoffs"))
               if cutoff_mode == "custom" else standard_cutoffs())
    return {
        "lab_name": lab_name,
        "default_organism": organism,
        "default_backend": backend,
        "strictness": strictness,
        "cutoff_mode": cutoff_mode,
        "cutoffs": cutoffs,
        "muse_base_url": str(payload.get("muse_base_url") or "").strip()[:_MAX_TEXT],
        "muse_model": str(payload.get("muse_model") or "").strip()[:_MAX_TEXT],
    }


def get_settings(user_id: int) -> dict[str, Any]:
    """Stored settings merged over defaults. Never includes the API key."""
    merged = dict(DEFAULT_SETTINGS)
    stored = db.get_user_settings(user_id)
    if stored:
        merged.update({k: stored[k] for k in DEFAULT_SETTINGS if k in stored})
    return merged


def get_muse_key(user_id: int) -> str:
    """The stored Muse API key for server-side calls (never API output)."""
    stored = db.get_user_settings(user_id) or {}
    return str(stored.get("muse_api_key") or "")


def muse_key_hint(user_id: int) -> dict[str, Any]:
    key = get_muse_key(user_id)
    return {"muse_key_set": bool(key), "muse_key_last4": key[-4:] if len(key) >= 4 else ""}


def save_settings(user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and store. Key handling: a non-empty muse_api_key replaces
    the stored key; clear_muse_key removes it; otherwise it is kept."""
    cleaned = validate_settings(payload)
    stored = db.get_user_settings(user_id) or {}
    if payload.get("clear_muse_key"):
        stored.pop("muse_api_key", None)
    elif str(payload.get("muse_api_key") or "").strip():
        stored["muse_api_key"] = str(payload["muse_api_key"]).strip()[:_MAX_KEY]
    stored.update(cleaned)
    db.save_user_settings(user_id, stored)
    return cleaned


def apply_strictness(params: dict[str, Any], strictness: str | None) -> dict[str, Any]:
    """Apply the preset's submission threshold to one search's parameters.

    Pure. The short-query profile (blast_params.py, Lab 04 Q1) is never
    overridden: a short query cannot reach a high score, so capping its
    threshold would return nothing. Classification thresholds (§7) are
    untouched in every branch.
    """
    preset = STRICTNESS_PRESETS.get((strictness or "balanced").lower())
    out = dict(params)
    if preset is None:
        out["strictness_preset"] = "balanced"
        return out
    out["strictness_preset"] = (strictness or "balanced").lower()
    threshold = preset["evalue_threshold"]
    if threshold is not None and not out.get("short_query_adjusted"):
        out["evalue_threshold"] = threshold
        out["strictness_note"] = (
            f"Submission E-value threshold set to {threshold:g} by the "
            f"{out['strictness_preset']} preset (Settings). Significance "
            "cut-offs are unchanged."
        )
    return out


def classification_cutoffs() -> dict[str, float]:
    """Back-compat alias: the standard §7 cut-offs."""
    return standard_cutoffs()


def job_cutoffs(settings: dict[str, Any]) -> dict[str, Any]:
    """The cut-off snapshot stamped onto a new job (mode + exact values)."""
    if settings.get("cutoff_mode") == "custom":
        return {"mode": "custom", **settings["cutoffs"]}
    return {"mode": "standard", **standard_cutoffs()}


# --- Local BLAST setup assistant (demo showcase) ---

DATABASE_OPTIONS: dict[str, dict[str, str]] = {
    "swissprot": {
        "label": "Swiss-Prot (recommended first database)",
        "size": "~570k curated proteins; small, fast, the current local copy",
        "source": "UniProtKB/Swiss-Prot FASTA via NCBI BLAST database FTP",
    },
    "refseq_protein": {
        "label": "RefSeq Protein (bigger, slower)",
        "size": "Much larger; covers RefSeq accessions such as NP_000509",
        "source": "NCBI RefSeq protein collection",
    },
    "custom_fasta": {
        "label": "My own FASTA file",
        "size": "Your sequences only; smallest and fully private",
        "source": "A FASTA file you provide, built with makeblastdb",
    },
}


def setup_plan(database_choice: str = "swissprot") -> dict[str, Any]:
    """Deterministic setup plan from live machine checks (no side effects).

    Steps report real status (BLAST+ found, database ready). The same
    step ids execute for real in setup_runner; the assistant only
    explains and guides.
    """
    choice = DATABASE_OPTIONS.get(database_choice) or DATABASE_OPTIONS["swissprot"]
    status = setup_status()
    steps = [
        {"id": "check_blast", "title": "Check BLAST+ programs",
         "status": "done" if status["blast_plus_installed"] else "needed",
         "detail": ("blastp/blastn found on this machine."
                    if status["blast_plus_installed"] else
                    "Install NCBI BLAST+ (apt install ncbi-blast+, or the Docker backend image which includes it).")},
        {"id": "choose_db", "title": f"Choose database: {choice['label']}",
         "status": "done", "detail": f"{choice['size']}. Source: {choice['source']}."},
        {"id": "download", "title": "Download the database files",
         "status": "done" if status["local_db_ready"] else "needed",
         "detail": "Fetches SwissProt FASTA and NCBI taxonomy, then extracts them. Runs from the Run setup button."},
        {"id": "build", "title": "Build the search database (makeblastdb)",
         "status": "done" if status["local_db_ready"] else "pending",
         "detail": "Runs makeblastdb with the taxonomy map derived from FASTA headers, then proves it with blastdbcmd. Runs from the Run setup button."},
        {"id": "verify", "title": "Verify with a sample search",
         "status": "done" if status["local_db_ready"] else "pending",
         "detail": (f"Local database ready at {status['blastdb_path']}."
                    if status["local_db_ready"] else
                    "Runs one known accession (P68871) and checks the top hit before the database is trusted.")},
    ]
    return {"database": database_choice, "steps": steps, "setup": status}


def setup_assistant_reply(*, database_choice: str, question: str,
                          plan: dict[str, Any]) -> str:
    """Deterministic demo reply (used when no live model call is made)."""
    pending = [s["title"] for s in plan["steps"] if s["status"] in ("needed", "pending", "demo_only")]
    lines = [
        "Here is your local BLAST setup plan. I guide and explain; WhatsGene code does every download, build, and check.",
    ]
    for step in plan["steps"]:
        mark = {"done": "Done", "needed": "Needed", "pending": "Later", "demo_only": "Demo only"}[step["status"]]
        lines.append(f"- [{mark}] {step['title']} — {step['detail']}")
    if question.strip():
        lines.append(f"You asked: {question.strip()[:200]}")
    if pending:
        lines.append("Next: " + pending[0] + ". Press Run setup now and WhatsGene executes it.")
    else:
        lines.append("Everything is ready — local searches will run in seconds on this machine.")
    return "\n".join(lines)


def setup_status() -> dict[str, Any]:
    """Plain-language readiness of the local search setup (no side effects)."""
    import os
    import shutil
    from pathlib import Path

    blastdb = os.environ.get("BLASTDB", "").strip()
    db_dir = Path(blastdb) if blastdb else Path.home() / "blastdb"
    db_ready = bool(db_dir.is_dir() and any(db_dir.glob("swissprot.*")))
    return {
        "search_backend": config.SEARCH_BACKEND,
        "blast_plus_installed": shutil.which("blastp") is not None,
        "blastdb_path": str(db_dir),
        "local_db_ready": bool(db_ready),
    }


def public_settings(user_id: int) -> dict[str, Any]:
    """Everything the Settings page needs in one response (key excluded)."""
    return {
        "settings": get_settings(user_id),
        **muse_key_hint(user_id),
        "presets": {
            key: {"label": p["label"], "help": p["help"],
                  "evalue_threshold": p["evalue_threshold"]}
            for key, p in STRICTNESS_PRESETS.items()
        },
        "standard_cutoffs": standard_cutoffs(),
        "database_options": DATABASE_OPTIONS,
        "setup": setup_status(),
        "server_model": {"model": config.MUSE_MODEL, "configured": bool(config.MUSE_API_KEY)},
    }
