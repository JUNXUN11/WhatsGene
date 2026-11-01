"""Configuration from environment variables (PRD §6: self-hostable).

Significance thresholds live here / in classify.py — never in model prompts.
Traceable to docs/blast-rules.md §6.
"""
from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv() -> None:
    """Load backend/.env into os.environ (no new dependency).

    Process env wins: only keys that are unset or blank are filled in.
    """
    dotenv = Path(__file__).resolve().parent.parent / ".env"
    if not dotenv.is_file():
        return
    for raw_line in dotenv.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name, value = name.strip(), value.strip().strip("'\"")
        if name and not os.environ.get(name):
            os.environ[name] = value


_load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# --- NCBI ---
NCBI_EMAIL: str = _env("NCBI_EMAIL")
NCBI_TOOL: str = _env("NCBI_TOOL", "WhatsGene")
NCBI_API_KEY: str = _env("NCBI_API_KEY")

# --- Search backend selection (app/search_backend.py) ---
# local (default): BLAST+ against $BLASTDB/swissprot. ncbi: opt-in remote
# (polite: 1 in-flight RID, polls >= 60s apart, aborts after 30 min).
# fixture: recorded JSON from tests/fixtures (tests and demo).
SEARCH_BACKEND: str = _env("SEARCH_BACKEND", "local")
BLASTDB: str = _env("BLASTDB")
FIXTURE_CASE: str = _env("FIXTURE_CASE", "")
NCBI_POLL_INTERVAL_SECONDS: float = float(_env("NCBI_POLL_INTERVAL_SECONDS", "60") or "60")
NCBI_MAX_WAIT_SECONDS: int = int(_env("NCBI_MAX_WAIT_SECONDS", "1800") or "1800")
LOCAL_BLAST_TIMEOUT_SECONDS: float = float(_env("LOCAL_BLAST_TIMEOUT_SECONDS", "600") or "600")

# --- URLs / storage ---
PUBLIC_BASE_URL: str = _env("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
FRONTEND_BASE_URL: str = _env("FRONTEND_BASE_URL", "http://localhost:3000").rstrip("/")
DATABASE_PATH: Path = Path(_env("DATABASE_PATH", "./whatsgene.db"))

# --- Model Ask guardrails (decision 007): quotas, cache, kill switch ---
MODEL_ASK_ENABLED: bool = _env("MODEL_ASK_ENABLED", "false").lower() in ("1", "true", "yes")
ASK_DAILY_LIMIT: int = int(_env("ASK_DAILY_LIMIT", "20") or "20")
JOBS_DAILY_LIMIT: int = int(_env("JOBS_DAILY_LIMIT", "10") or "10")
MODEL_MAX_TOKENS: int = int(_env("MODEL_MAX_TOKENS", "400") or "400")
MODEL_TIMEOUT_SECONDS: float = float(_env("MODEL_TIMEOUT_SECONDS", "60") or "60")

# --- Auth: one seeded user, no signup (decision 007) ---
AUTH_USERNAME: str = _env("AUTH_USERNAME", "reviewer")
AUTH_PASSWORD: str = _env("AUTH_PASSWORD")
COOKIE_SECURE: bool = _env("COOKIE_SECURE", "false").lower() in ("1", "true", "yes")

# --- WhatsApp Cloud API ---
WHATSAPP_TOKEN: str = _env("WHATSAPP_TOKEN")
WHATSAPP_PHONE_NUMBER_ID: str = _env("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_VERIFY_TOKEN: str = _env("WHATSAPP_VERIFY_TOKEN", "change-me")
WHATSAPP_TEMPLATE_NAME: str = _env("WHATSAPP_TEMPLATE_NAME", "whatsgene_job_done")

# --- Agent layer: Muse Spark Open via Modal Shared Endpoint (PRD §8) ---
# OpenAI-compatible endpoint. URL and model name are env-configurable.
MUSE_BASE_URL: str = _env("MUSE_BASE_URL", _env("MODAL_BASE_URL"))
MUSE_API_KEY: str = _env("MUSE_API_KEY")
MUSE_MODEL: str = _env("MUSE_MODEL", "muse-spark-open")

# --- Agent-loop run budget (PRD §4.1; defaults open — PRD Open questions #1) ---
MAX_SEARCHES_PER_JOB: int = int(_env("MAX_SEARCHES_PER_JOB", "6") or "6")
MAX_JOB_SECONDS: int = int(_env("MAX_JOB_SECONDS", "1800") or "1800")

# Whether a logged model deviation applies without user confirmation.
# Open in PRD (Open questions #7); default keeps the rules-engine choice.
DEVIATION_AUTO_APPLY: bool = _env("DEVIATION_AUTO_APPLY", "false").lower() in ("1", "true", "yes")

# Verification: query/subject length ratio above this flags a mismatch (§8).
VERIFY_MAX_LENGTH_RATIO: float = float(_env("VERIFY_MAX_LENGTH_RATIO", "3") or "3")

# --- Classification thresholds (docs/blast-rules.md §6) ---
# Implemented in code/config only. Change here, not in prompts.
STRONG_MAX_EVALUE: float = 1e-5
STRONG_MIN_COVERAGE: float = 70.0  # percent
BORDERLINE_MAX_EVALUE: float = 1e-2
BORDERLINE_MIN_COVERAGE: float = 30.0  # percent; below this = not significant

# --- Worker / NCBI polling etiquette ---
POLL_INTERVAL_SECONDS: float = 15.0
POLL_BACKOFF_MAX_SECONDS: float = 120.0
# How many workflows run at once. NcbiRemote is forced to 1 in the worker
# (one in-flight RID etiquette); local/fixture workflows may run in parallel.
MAX_CONCURRENT_JOBS: int = int(_env("MAX_CONCURRENT_JOBS", "3") or "3")
